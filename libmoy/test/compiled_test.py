#!/usr/bin/env python3
"""The compiled-cart authoring loop, through the real CLI.

    python3 test/compiled_test.py              # everything
    python3 test/compiled_test.py --offline    # no toolchain, no network

Offline, it needs nothing but Python: `moy new --wasm` scaffolds a cart whose
header is libmoy's own moy_cart.h; `moy pack` takes a compiled cart; `moy
index` writes a carts repository's index, its cover entry and an external
file's mirror included, and `moy install` installs from it -- an external
file from its mirror first and its archive after -- refusing an asset that is
not the one the index names and leaving the destination untouched; `moy push` over serial sends a compiled cart without
its src/ and shows what the console notes.

With the toolchain -- $WASI_SDK_PATH, or the pinned wasi-sdk `moy build
--toolchain` fetches -- it builds both starters (`--jet` fetches Jet at its
pin, so this half needs the network the first time), holds each module to
SPEC.md 16 through `moy check`, plays each in the desktop player when one is
built, and holds `moy build` to what it promises when a cart is wrong: the
compiler's own words, a module that reaches for WASI refused by name, a
memory too small for the stack and data, and the last good module left in
place. Run by `make compiled-test`.
"""
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
LIBMOY = os.path.dirname(HERE)
ROOT = os.path.dirname(LIBMOY)
MOY = os.path.join(ROOT, "moy.py")
PLAYER = os.path.join(LIBMOY, "build", "moy-play")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import compiled                               # noqa: E402
import wat                                    # noqa: E402

FAILS = []


def fail(msg):
    FAILS.append(msg)
    print("  FAIL " + msg)


def ok(msg):
    print("  ok   " + msg)


def moy(*args, cwd=None, env=None):
    r = subprocess.run([sys.executable, MOY] + list(args), capture_output=True,
                       text=True, cwd=cwd, env=env)
    return r.returncode, r.stdout + r.stderr


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# -- offline ------------------------------------------------------------------


def scaffold(tmp):
    rc, out = moy("new", "--wasm", "first_light", cwd=tmp)
    cart = os.path.join(tmp, "first_light.moy")
    if rc != 0:
        return fail("moy new --wasm: %s" % out)
    with open(os.path.join(cart, "manifest.json")) as f:
        man = json.load(f)
    want = {"runtime": "wasm", "main": "main.wasm", "title": "First Light"}
    if any(man.get(k) != v for k, v in want.items()) or not isinstance(man.get("memory"), int):
        fail("the starter's manifest is %r" % man)
    if sha256(os.path.join(cart, "src", "moy_cart.h")) != \
            sha256(os.path.join(LIBMOY, "include", "moy_cart.h")):
        fail("the starter's moy_cart.h is not libmoy's")
    for name in ("main.c", "runtime.c"):
        if not os.path.isfile(os.path.join(cart, "src", name)):
            fail("the starter has no src/%s" % name)
    rc, out = moy("new", "--wasm", "first_light", cwd=tmp)
    if rc == 0 or "already exists" not in out:
        fail("moy new over an existing cart: %s" % out)
    if compiled._c_string('50% "fun"\\') != '50%% \\"fun\\"\\\\':
        fail("a title is not escaped for the C string it lands in")
    ok("moy new --wasm scaffolds a cart around libmoy's moy_cart.h")


def pack_compiled(tmp):
    cart = os.path.join(tmp, "hello.moy")
    wat.build_cart(os.path.join(HERE, "wasm", "hello.moy"), cart)
    rc, out = moy("pack", cart, os.path.join(tmp, "hello.moyc"))
    if rc != 0:
        return fail("moy pack refuses a compiled cart: %s" % out)
    bad = os.path.join(tmp, "bad.moy")
    wat.build_cart(os.path.join(HERE, "wasm", "foreign_import.moy"), bad)
    rc, out = moy("pack", bad, os.path.join(tmp, "bad.moyc"))
    if rc == 0 or "wasm.import" not in out:
        return fail("moy pack took a compiled cart that does not load: %s" % out)
    ok("moy pack takes a compiled cart and refuses one SPEC.md 16 refuses")


def carts_repo(tmp):
    """A carts repository with one built cart, then index -> install."""
    repo = os.path.join(tmp, "repo")
    cart_dir = os.path.join(repo, "carts", "blink")
    os.makedirs(cart_dir)
    with open(os.path.join(cart_dir, "NOTICE"), "w") as f:
        f.write("MIT, by the test.\n")
    meta = {"id": "blink", "name": "Blink", "version": 1, "release": "blink-v1",
            "folder": "blink.moy", "chips": [], "licence": {"spdx": "MIT", "file": "NOTICE"}}
    with open(os.path.join(cart_dir, "cart.json"), "w") as f:
        json.dump(meta, f)
    files = {"manifest.json": b'{"format": "moy-1", "title": "Blink"}\n',
             "main.lua": b"function _draw() cls(8) end\n"}
    with open(os.path.join(cart_dir, "manifest.json"), "wb") as f:
        f.write(files["manifest.json"])
    dist = os.path.join(repo, "build", "dist", "blink")
    os.makedirs(dist)
    zpath = os.path.join(dist, "blink.moy.zip")
    with zipfile.ZipFile(zpath, "w") as z:
        for name, data in sorted(files.items()):
            z.writestr("blink.moy/" + name, data)
    with open(zpath, "rb") as f:
        blob = f.read()
    built = {"id": "blink", "commit": "0" * 40, "source": "https://example.invalid/blink",
             "asset": {"name": "blink.moy.zip", "size": len(blob),
                       "sha256": hashlib.sha256(blob).hexdigest()},
             "files": {n: {"size": len(d), "sha256": hashlib.sha256(d).hexdigest()}
                       for n, d in files.items()}}
    with open(os.path.join(dist, "build.json"), "w") as f:
        json.dump(built, f)

    rc, out = moy("index", repo)
    if rc == 0:
        fail("moy index wrote a new index with no --name/--home: %s" % out)
    rc, out = moy("index", repo, "--name", "Test carts",
                  "--home", "https://example.invalid/carts")
    if rc != 0:
        return fail("moy index: %s" % out)
    with open(os.path.join(repo, "index.json")) as f:
        index = json.load(f)
    entry = index["carts"][0]
    if (index["name"], entry["id"], entry["runtime"], entry["licence"]["spdx"]) != \
            ("Test carts", "blink", "lua", "MIT") or \
            entry["assets"][0]["url"] != \
            "https://example.invalid/carts/releases/download/blink-v1/blink.moy.zip":
        fail("the index says %r" % entry)
    if "cover" in entry:
        fail("a cart with no cover.png has a cover entry: %r" % entry["cover"])
    rc, out = moy("index", repo)
    if rc != 0:
        fail("moy index again, from the index it wrote: %s" % out)
    ok("moy index writes a carts repository's index.json")

    # The cover is the repository's file, read on every run, built or not.
    with open(os.path.join(ROOT, "conformance", "covers", "indexed_filter4.png"), "rb") as f:
        cover = f.read()
    with open(os.path.join(cart_dir, "cover.png"), "wb") as f:
        f.write(cover)
    os.rename(os.path.join(dist, "build.json"), os.path.join(tmp, "build.json"))
    rc, out = moy("index", repo)
    with open(os.path.join(repo, "index.json")) as f:
        entry = json.load(f)["carts"][0]
    want = {"url": "carts/blink/cover.png", "size": len(cover),
            "sha256": hashlib.sha256(cover).hexdigest(), "w": 128, "h": 128}
    if rc != 0 or entry.get("cover") != want:
        fail("moy index on a cart not built here gave the cover %r: %s"
             % (entry.get("cover"), out))
    os.rename(os.path.join(tmp, "build.json"), os.path.join(dist, "build.json"))
    with open(os.path.join(ROOT, "conformance", "covers", "size_127x128.png"), "rb") as f:
        bad = f.read()
    with open(os.path.join(cart_dir, "cover.png"), "wb") as f:
        f.write(bad)
    rc, out = moy("index", repo)
    if rc == 0 or "moy build" not in out:
        fail("moy index took a cover outside the profile: %s" % out)
    with open(os.path.join(cart_dir, "cover.png"), "wb") as f:
        f.write(cover)
    rc, out = moy("index", repo)
    with open(os.path.join(repo, "index.json")) as f:
        index = json.load(f)
    entry = index["carts"][0]
    if rc != 0 or entry.get("cover") != want:
        fail("moy index on a built cart gave the cover %r: %s" % (entry.get("cover"), out))
    ok("moy index names the cover beside the licence, built or not, and refuses one "
       "outside the profile")

    # The mirror: a copy of each release asset beside the index, for a browser.
    rc, out = moy("index", repo, "--mirror", "releases")
    with open(os.path.join(repo, "index.json")) as f:
        asset = json.load(f)["carts"][0]["assets"][0]
    if rc != 0 or asset.get("mirror") != "releases/blink-v1/blink.moy.zip":
        fail("moy index --mirror gave %r: %s" % (asset.get("mirror"), out))
    os.rename(os.path.join(dist, "build.json"), os.path.join(tmp, "build.json"))
    rc, out = moy("index", repo)
    os.rename(os.path.join(tmp, "build.json"), os.path.join(dist, "build.json"))
    with open(os.path.join(repo, "index.json")) as f:
        asset = json.load(f)["carts"][0]["assets"][0]
    if rc != 0 or asset.get("mirror") != "releases/blink-v1/blink.moy.zip":
        fail("moy index without --mirror, on a cart not built here, gave the mirror %r: %s"
             % (asset.get("mirror"), out))
    rc, out = moy("index", repo, "--mirror", "../elsewhere")
    if rc == 0 or "relative" not in out:
        fail("moy index took a mirror folder outside the site: %s" % out)
    rc, out = moy("index", repo)
    with open(os.path.join(repo, "index.json")) as f:
        index = json.load(f)
    entry = index["carts"][0]
    if rc != 0 or entry["assets"][0].get("mirror") != "releases/blink-v1/blink.moy.zip":
        fail("moy index lost the mirror: %s" % out)
    ok("moy index names each release asset's mirror under --mirror, built or not, and "
       "keeps the folder the index already uses")

    # The release carries the cover like any other file.
    files["cover.png"] = cover
    with zipfile.ZipFile(zpath, "w") as z:
        for name, data in sorted(files.items()):
            z.writestr("blink.moy/" + name, data)
    with open(zpath, "rb") as f:
        blob = f.read()
    entry["assets"][0].update(size=len(blob), sha256=hashlib.sha256(blob).hexdigest(),
                              files={n: {"size": len(d), "sha256": hashlib.sha256(d).hexdigest()}
                                     for n, d in files.items()})
    with open(os.path.join(repo, "index.json"), "w") as f:
        json.dump(index, f)

    dest = os.path.join(tmp, "card")
    os.makedirs(dest)
    idx = os.path.join(repo, "index.json")
    rc, out = moy("install", "--index", idx, "--list")
    if rc != 0 or "blink" not in out:
        fail("moy install --list: %s" % out)
    rc, out = moy("install", "--index", idx, "blink", dest, "--asset-dir", dist)
    got = sorted(os.listdir(os.path.join(dest, "blink.moy"))) if rc == 0 else None
    if got != sorted(files):
        return fail("moy install: rc=%d %s %s" % (rc, got, out))
    with open(zpath, "ab") as f:
        f.write(b"tampered")
    shutil.rmtree(os.path.join(dest, "blink.moy"))
    rc, out = moy("install", "--index", idx, "blink", dest, "--asset-dir", dist)
    if rc == 0 or "Refusing" not in out or os.listdir(dest):
        return fail("moy install took an asset that is not the index's: %s" % out)
    ok("moy install installs from an index and refuses an asset it does not name")

    # The release is canonical; the mirror is where moy install goes when the
    # release does not answer. Here the release is a port nothing listens on and
    # the mirror is a file beside the index.
    site = os.path.join(tmp, "site")
    os.makedirs(os.path.join(site, "releases", "blink-v1"))
    good = os.path.join(tmp, "good.zip")
    with zipfile.ZipFile(good, "w") as z:
        for name, data in sorted(files.items()):
            z.writestr("blink.moy/" + name, data)
    with open(good, "rb") as f:
        blob = f.read()
    shutil.copy(good, os.path.join(site, "releases", "blink-v1", "blink.moy.zip"))
    shutil.copy(os.path.join(cart_dir, "NOTICE"), os.path.join(site, "NOTICE"))
    mirrored = json.loads(json.dumps(index))
    m_entry = mirrored["carts"][0]
    m_entry["licence"]["url"] = "NOTICE"
    m_entry["assets"][0].update(url="http://127.0.0.1:9/blink.moy.zip", size=len(blob),
                                sha256=hashlib.sha256(blob).hexdigest())
    m_idx = os.path.join(site, "index.json")
    with open(m_idx, "w") as f:
        json.dump(mirrored, f)
    rc, out = moy("install", "--index", m_idx, "blink", dest)
    if rc != 0 or sorted(os.listdir(os.path.join(dest, "blink.moy"))) != sorted(files):
        return fail("moy install did not fall back to the mirror: %s" % out)
    shutil.rmtree(os.path.join(dest, "blink.moy"))
    for bad in ("../blink.moy.zip", "https://elsewhere.example/blink.moy.zip",
                "releases/blink-v1/other.zip"):
        m_entry["assets"][0]["mirror"] = bad
        with open(m_idx, "w") as f:
            json.dump(mirrored, f)
        rc, out = moy("install", "--index", m_idx, "--list")
        if rc == 0 or "not a valid index" not in out:
            return fail("moy install read an index whose mirror is %r: %s" % (bad, out))
    ok("moy install falls back to an asset's mirror, and refuses an index whose mirror "
       "is not the asset beside it")

    # The same files, compressed: the index can name this asset exactly, and
    # it is still refused, because a console unpacks a release as it streams.
    packed = os.path.join(tmp, "packed")
    os.makedirs(packed)
    zpath = os.path.join(packed, "blink.moy.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(files.items()):
            z.writestr("blink.moy/" + name, data)
    with open(zpath, "rb") as f:
        blob = f.read()
    entry["assets"][0].update(size=len(blob), sha256=hashlib.sha256(blob).hexdigest())
    deflated = os.path.join(repo, "deflated.json")
    with open(deflated, "w") as f:
        json.dump(index, f)
    rc, out = moy("install", "--index", deflated, "blink", dest, "--asset-dir", packed)
    if rc == 0 or "STORED" not in out or os.listdir(dest):
        return fail("moy install took a compressed release asset: %s" % out)
    ok("moy install refuses a release asset that is not a STORED zip")


def external_mirror(tmp):
    """An external file the repository gives away itself: `moy index` names
    its mirror from cart.json, and `moy install` takes the bare file from it
    before the archive, and the archive when the mirror cannot be had."""
    import io
    import tarfile
    repo = os.path.join(tmp, "xrepo")
    cart_dir = os.path.join(repo, "carts", "dm")
    os.makedirs(os.path.join(cart_dir, "licenses"))
    data = b"IWAD" + bytes(range(256)) * 40
    member = "pkg-1.0/game.dat"
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w:gz") as t:
        info = tarfile.TarInfo(member)
        info.size = len(data)
        t.addfile(info, io.BytesIO(data))
    arc = raw.getvalue()
    with open(os.path.join(cart_dir, "NOTICE"), "w") as f:
        f.write("GPL-2.0-or-later, by the test.\n")
    with open(os.path.join(cart_dir, "licenses", "game.dat.txt"), "w") as f:
        f.write("You may give game.dat away, unmodified.\n")
    ext = {"path": "game.dat", "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
           "mirror": "files/dm/game.dat",
           "licence": {"name": "The game.dat licence", "file": "licenses/game.dat.txt"},
           "archive": {"urls": ["pkg.tar.gz"], "format": "tar.gz", "size": len(arc),
                       "sha256": hashlib.sha256(arc).hexdigest(), "member": member}}
    meta = {"id": "dm", "name": "DM", "version": 1, "release": "dm-v1", "folder": "dm.moy",
            "chips": [], "licence": {"spdx": "GPL-2.0-or-later", "file": "NOTICE"},
            "external": [ext]}
    with open(os.path.join(cart_dir, "cart.json"), "w") as f:
        json.dump(meta, f)
    files = {"manifest.json": b'{"format": "moy-1", "title": "DM"}\n',
             "main.lua": b"function _draw() cls(1) end\n"}
    with open(os.path.join(cart_dir, "manifest.json"), "wb") as f:
        f.write(files["manifest.json"])
    dist = os.path.join(repo, "build", "dist", "dm")
    os.makedirs(dist)
    zpath = os.path.join(dist, "dm.moy.zip")
    with zipfile.ZipFile(zpath, "w") as z:
        for name, body in sorted(files.items()):
            z.writestr("dm.moy/" + name, body)
    with open(zpath, "rb") as f:
        blob = f.read()
    with open(os.path.join(dist, "build.json"), "w") as f:
        json.dump({"id": "dm", "commit": "0" * 40, "source": "https://example.invalid/dm",
                   "asset": {"name": "dm.moy.zip", "size": len(blob),
                             "sha256": hashlib.sha256(blob).hexdigest()},
                   "files": {n: {"size": len(b), "sha256": hashlib.sha256(b).hexdigest()}
                             for n, b in files.items()}}, f)
    rc, out = moy("index", repo, "--name", "Test carts", "--home", "https://example.invalid/carts")
    idx = os.path.join(repo, "index.json")
    with open(idx) as f:
        index = json.load(f)
    got = index["carts"][0]["external"][0] if rc == 0 else {}
    if rc != 0 or got.get("mirror") != "files/dm/game.dat" \
            or list(got) != ["path", "size", "sha256", "mirror", "licence", "archive"]:
        return fail("moy index gave the external %r: %s" % (got, out))
    del meta["external"][0]["mirror"]
    with open(os.path.join(cart_dir, "cart.json"), "w") as f:
        json.dump(meta, f)
    os.rename(os.path.join(dist, "build.json"), os.path.join(tmp, "dm-build.json"))
    rc, out = moy("index", repo)
    with open(idx) as f:
        gone = json.load(f)["carts"][0]["external"][0]
    if rc != 0 or "mirror" in gone:
        fail("moy index kept a mirror cart.json no longer names: %r %s" % (gone, out))
    with open(idx, "w") as f:
        json.dump(index, f)
    ok("moy index names an external file's mirror where cart.json does, built or not")

    # The site: the index, the licences, the bare file at its mirror, and the
    # archive beside them. The release itself is a port nothing listens on.
    entry = index["carts"][0]
    entry["assets"][0]["url"] = "http://127.0.0.1:9/dm.moy.zip"
    entry["assets"][0]["mirror"] = "releases/dm-v1/dm.moy.zip"
    os.makedirs(os.path.join(repo, "releases", "dm-v1"))
    shutil.copy(zpath, os.path.join(repo, "releases", "dm-v1", "dm.moy.zip"))
    os.makedirs(os.path.join(repo, "files", "dm"))
    with open(os.path.join(repo, "files", "dm", "game.dat"), "wb") as f:
        f.write(data)
    with open(idx, "w") as f:
        json.dump(index, f)
    dest = os.path.join(tmp, "xcard")
    os.makedirs(dest)
    rc, out = moy("install", "--index", idx, "--list")
    if rc != 0 or "fetched from beside the index, else" not in out:
        fail("moy install --list does not say where game.dat comes from: %s" % out)
    rc, out = moy("install", "--index", idx, "dm", dest, "--yes")
    target = os.path.join(dest, "dm.moy", "game.dat")
    if rc != 0 or not os.path.isfile(target) or "trying its archive" in out \
            or "archive holding" in out:
        return fail("moy install did not take game.dat from its mirror: %s" % out)
    with open(target, "rb") as f:
        if f.read() != data:
            return fail("moy install wrote a game.dat that is not the index's")
    shutil.rmtree(os.path.join(dest, "dm.moy"))
    with open(os.path.join(repo, "pkg.tar.gz"), "wb") as f:
        f.write(arc)
    for broken in (b"not the file", None):
        if broken is None:
            os.remove(os.path.join(repo, "files", "dm", "game.dat"))
        else:
            with open(os.path.join(repo, "files", "dm", "game.dat"), "wb") as f:
                f.write(broken)
        rc, out = moy("install", "--index", idx, "dm", dest, "--yes")
        if rc != 0 or "trying its archive" not in out or not os.path.isfile(target):
            return fail("moy install did not fall back to the archive: %s" % out)
        shutil.rmtree(os.path.join(dest, "dm.moy"))
    old = json.loads(json.dumps(index))
    del old["carts"][0]["external"][0]["mirror"]
    with open(idx, "w") as f:
        json.dump(old, f)
    rc, out = moy("install", "--index", idx, "dm", dest, "--yes")
    if rc != 0 or "trying its archive" in out or not os.path.isfile(target):
        return fail("moy install of an index without the mirror: %s" % out)
    shutil.rmtree(os.path.join(dest, "dm.moy"))
    ok("moy install takes an external file from its mirror, bare, and from its archive "
       "when the mirror is wrong, gone or not named")
    for bad in ("../game.dat", "https://elsewhere.example/game.dat", "files/dm/other.dat"):
        index["carts"][0]["external"][0]["mirror"] = bad
        with open(idx, "w") as f:
            json.dump(index, f)
        rc, out = moy("install", "--index", idx, "--list")
        if rc == 0 or "not a valid index" not in out:
            return fail("moy install read an index whose external mirror is %r: %s"
                        % (bad, out))
    ok("moy install refuses an index whose external mirror is not the file beside it")


class FakeConsole(object):
    """A console answering proposals/sideload.md's tier 1, as a pyserial
    port: it decodes what is written, keeps the files, and answers."""

    def __init__(self):
        self.files, self.replies, self.buf = {}, [], b""
        self.put = None

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def write(self, data):
        import base64
        self.buf += data
        while b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            text = line.decode()
            if self.put is not None:
                if text == ".":
                    path, size, chunks = self.put
                    data = b"".join(chunks)
                    self.files[path] = data
                    self.put = None
                    if path.endswith(".wasm"):
                        self.replies.append(b"moy-note no module for this chip\n")
                    self.replies.append(b"moy-ok\n" if len(data) == size
                                        else b"moy-err short\n")
                else:
                    self.put[2].append(base64.b64decode(text))
            elif text.startswith("moy-put "):
                _, path, size = text.split()
                self.put = (path, int(size), [])
                self.replies.append(b"moy-ok\n")
            elif text == "moy-rescan":
                self.replies.append(b"booting... noise\n")
                # Logging that was mid-line when the reply was written.
                self.replies.append(b"PERF fps=0/60 flush=0moy-ok\n")

    def readline(self):
        return self.replies.pop(0) if self.replies else b""


def push_over_serial(tmp):
    """`moy push` over tier 1 to a console that answers it: every file of a
    compiled cart but its src/, and the console's notes shown to the person."""
    import sideload
    cart = os.path.join(tmp, "hello_push.moy")
    wat.build_cart(os.path.join(HERE, "wasm", "hello.moy"), cart)
    os.makedirs(os.path.join(cart, "src"), exist_ok=True)
    with open(os.path.join(cart, "src", "main.c"), "w") as f:
        f.write("/* the source stays home */\n")
    fake = FakeConsole()
    module = type("serial", (), {"Serial": fake})
    said = []
    real = sideload._serial_module
    sideload._serial_module = lambda: module
    try:
        sideload.push_serial("/dev/fake", cart, log=said.append)
    finally:
        sideload._serial_module = real
    got = sorted(fake.files)
    want = sorted("hello_push.moy/" + f for f in os.listdir(cart) if f != "src")
    if got != want:
        return fail("moy push over serial sent %s, not %s" % (got, want))
    if not any("no module for this chip" in line for line in said):
        return fail("a console's moy-note was not shown: %s" % said)
    ok("moy push over tier 1: the cart without its src/, and the console's notes shown")


# -- with the toolchain ---------------------------------------------------------


def frame_colours(cart, tmp):
    """The number of colours in the frame the desktop player shows after two
    ticks, or None where no player is built."""
    if not os.path.isfile(PLAYER):
        return None
    out = os.path.join(tmp, "frame.bin")
    env = dict(os.environ, SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    r = subprocess.run([PLAYER, cart, "--dump", out], capture_output=True, text=True,
                       env=env, timeout=120)
    if r.returncode != 0:
        fail("moy-play %s: %s" % (cart, r.stdout + r.stderr))
        return 0
    with open(out, "rb") as f:
        data = f.read()
    return len(set(struct.unpack("<%dH" % (len(data) // 2), data)))


def check_clean(cart):
    rc, out = moy("check", cart)
    findings = [ln for ln in out.splitlines() if ln.strip().startswith(("error", "warn"))]
    if rc != 0 or findings:
        fail("moy check %s: %s" % (cart, out))
        return False
    return True


def build_starters(tmp, jet):
    kinds = ["wasm"] + (["jet"] if jet else [])
    for kind in kinds:
        cart = os.path.join(tmp, "starter_%s.moy" % kind)
        rc, out = moy("new", "--" + kind, cart)
        if rc != 0:
            fail("moy new --%s: %s" % (kind, out))
            continue
        rc, out = moy("build", cart)
        main = os.path.join(cart, "main.wasm")
        if rc != 0 or not os.path.isfile(main):
            fail("moy build the %s starter: %s" % (kind, out))
            continue
        with open(main, "rb") as f:
            imports = compiled.module_imports(f.read())
        if not imports or any(m != "moy" for m, _ in imports):
            fail("the %s starter imports %s" % (kind, imports))
        if not check_clean(cart):
            continue
        colours = frame_colours(cart, tmp)
        if colours is not None and colours < (64 if kind == "wasm" else 3):
            fail("the %s starter's frame has %d colours" % (kind, colours))
        ok("the %s starter builds, imports only \"moy\", passes moy check%s"
           % (kind, "" if colours is None else ", and plays (%d colours)" % colours))
    return os.path.join(tmp, "starter_wasm.moy")


def build_refusals(cart):
    main = os.path.join(cart, "main.wasm")
    src = os.path.join(cart, "src", "main.c")
    good = sha256(main)
    rc, out = moy("build", cart)
    if rc != 0 or sha256(main) != good:
        fail("an unchanged rebuild: rc=%d %s" % (rc, out))
    with open(src) as f:
        text = f.read()

    def attempt(edit, why, words):
        with open(src, "w") as f:
            f.write(edit)
        rc, out = moy("build", cart)
        if rc == 0 or not all(w in out for w in words) or sha256(main) != good:
            fail("%s: rc=%d, the module %s:\n%s"
                 % (why, rc, "kept" if sha256(main) == good else "replaced", out))
        else:
            ok("moy build refuses %s, and keeps the last good module" % why)

    attempt(text + "\nint broken(void) { return }\n", "a syntax error",
            ["main.c", "error"])
    attempt(text.replace("#include <stdio.h>", "#include <stdio.h>\n#include <stdlib.h>")
            + '\nMOY_EXPORT("probe") int probe(void) { return getenv("HOME") != 0; }\n',
            "a module that reaches for WASI", ["wasi_snapshot_preview1", "moy_time()"])
    with open(src, "w") as f:
        f.write(text)
    man_path = os.path.join(cart, "manifest.json")
    with open(man_path) as f:
        man = json.load(f)
    small = dict(man, memory=1)
    with open(man_path, "w") as f:
        json.dump(small, f)
    rc, out = moy("build", cart)
    if rc == 0 or "raise it to at least" not in out:
        fail("a memory too small for the stack and data: %s" % out)
    else:
        ok("moy build names the memory a cart's stack and data need")
    with open(man_path, "w") as f:
        json.dump(man, f)
    rc, out = moy("build", cart)
    if rc != 0 or sha256(main) != good:
        fail("the restored cart does not build its module again: %s" % out)


def main():
    offline = "--offline" in sys.argv
    tmp = tempfile.mkdtemp(prefix="moy-compiled-")
    try:
        print("compiled carts: offline")
        scaffold(tmp)
        pack_compiled(tmp)
        carts_repo(tmp)
        external_mirror(tmp)
        push_over_serial(tmp)
        if offline:
            print("compiled carts: (skipping the toolchain half: --offline)")
        else:
            print("compiled carts: with the toolchain")
            try:
                print("  toolchain %s" % compiled.fetch_sdk())
            except compiled.BuildError as exc:
                fail("no toolchain: %s" % exc)
            else:
                cart = build_starters(tmp, jet=True)
                if os.path.isfile(os.path.join(cart, "main.wasm")):
                    build_refusals(cart)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if FAILS:
        sys.exit("compiled carts: %d failure%s" % (len(FAILS), "" if len(FAILS) == 1 else "s"))
    print("compiled carts: new, build, pack, index and install behave")


if __name__ == "__main__":
    main()
