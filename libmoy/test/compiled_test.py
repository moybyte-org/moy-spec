#!/usr/bin/env python3
"""The compiled-cart authoring loop, through the real CLI.

    python3 test/compiled_test.py              # everything
    python3 test/compiled_test.py --offline    # no toolchain, no network

Offline, it needs nothing but Python: `moy new --wasm` scaffolds a cart whose
header is libmoy's own moy_cart.h; `moy pack` takes a compiled cart; `moy
index` writes a carts repository's index, its cover entry included, and `moy
install` installs from it, refusing an asset that is not the one the index
names and leaving the destination untouched; `moy push` over serial sends a compiled cart without
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
