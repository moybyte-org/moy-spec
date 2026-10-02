#!/usr/bin/env python3
"""Covers (SPEC.md 3.6): the reference reader against the vectors, and the
writer, the squaring and the rewrite that the CLI is built on.

  * conformance/covers/: expected.json is what its build.py writes, every file
    is the size it says, and moycore.cover.read gives each file's verdict --
    for a cover, the pixels whose sha256 the vectors name.
  * moycore.png.encode and moycore.cover.encode write what read gives back,
    indexed at 256 colours or fewer and RGB above.
  * moycore.cover.square: a 128x128 picture is untouched, a multiple of 128
    is sampled every k-th pixel, anything else is the centre square
    area-averaged, all checked against a direct computation here.
  * moycore.cover.rewrite brings every vector a PNG decoder can read into the
    profile.
  * the CLI: `moy check` warns about a cover outside the profile and the cart
    stays valid; `moy build` rewrites one into it, Lua cart or compiled;
    `moy play`'s watcher rewrites what moy-play's F7 writes, smaller and with
    the same pixels.
  * moy-play, when it is built: F7's writer through --dump --cover, at every
    canvas size and for a compiled cart, against moycore's squaring of the
    frame --dump writes raw.

Run by `make cover-test`.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
VECTORS = os.path.join(ROOT, "conformance", "covers")
MOY = os.path.join(ROOT, "moy.py")
PLAYER = os.path.join(os.path.dirname(HERE), "build", "moy-play")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

from moycore import cover, palette            # noqa: E402

FAILS = []


def fail(msg):
    FAILS.append(msg)
    print("  FAIL " + msg)


def ok(msg):
    print("  ok   " + msg)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def vectors():
    r = subprocess.run([sys.executable, os.path.join(VECTORS, "build.py"), "--check"],
                       capture_output=True, text=True)
    if r.returncode:
        fail(r.stdout + r.stderr)
    with open(os.path.join(VECTORS, "expected.json"), encoding="utf-8") as f:
        want = json.load(f)["vectors"]
    on_disk = sorted(n for n in os.listdir(VECTORS) if n.endswith(".png"))
    if on_disk != sorted(v["file"] for v in want):
        fail("the vector files are not expected.json's")
    seen = {"cover": 0, "ignored": 0}
    for v in want:
        with open(os.path.join(VECTORS, v["file"]), "rb") as f:
            data = f.read()
        if len(data) != v["bytes"]:
            fail("%s is %d bytes; expected.json says %d" % (v["file"], len(data), v["bytes"]))
        try:
            got = sha(cover.read(data))
        except cover.CoverError as exc:
            got = "ignored (%s)" % exc
        if v["verdict"] == "cover" and got != v["rgb888_sha256"]:
            fail("%s should be a cover with pixels %s; read says %s"
                 % (v["file"], v["rgb888_sha256"][:12], got))
        elif v["verdict"] == "ignored" and not got.startswith("ignored"):
            fail("%s should be ignored; read takes it as a cover" % v["file"])
        else:
            seen[v["verdict"]] += 1
        if v["verdict"] == "ignored":
            continue
        out, notes = cover.rewrite(data)
        if cover.read(out) != cover.read(data):
            fail("rewrite changed %s's pixels" % v["file"])
    ok("conformance/covers: %d covers and %d ignored files, each as expected.json says"
       % (seen["cover"], seen["ignored"]))


def picture(w, h, colours):
    out = bytearray()
    for y in range(h):
        for x in range(w):
            c = (x * 7 + y * 3 + (x * y) % 5) % colours
            out.extend(((c * 37) & 255, (c * 91) & 255, (c * 13 + c // 256) & 255))
    return bytes(out)


def writer():
    for colours, ctype in ((1, 3), (200, 3), (256, 3), (257, 2), (4000, 2)):
        pic = picture(128, 128, colours)
        distinct = len(set(pic[i:i + 3] for i in range(0, len(pic), 3)))
        data = cover.encode(pic)
        if data[25] != (3 if distinct <= 256 else 2):
            fail("%d colours encoded as colour type %d" % (distinct, data[25]))
        if cover.problem(data) or cover.read(data) != pic:
            fail("encode of %d colours does not read back: %s"
                 % (distinct, cover.problem(data)))
        if cover.encode(pic) != data:
            fail("encode is not deterministic")
    ok("encode writes indexed to 256 colours and RGB above, and reads back")


def area_average(w, h, rgb):
    """SPEC.md 3.6's reduction, written out the slow way: every output pixel
    against every source pixel of the centre square."""
    side = min(w, h)
    x0, y0 = (w - side) // 2, (h - side) // 2

    def overlap(o, i):
        return max(0, min((o + 1) * side, (i + 1) * 128) - max(o * side, i * 128))
    out = bytearray()
    for oy in range(128):
        ys = [(i, overlap(oy, i)) for i in range(side) if overlap(oy, i)]
        for ox in range(128):
            xs = [(i, overlap(ox, i)) for i in range(side) if overlap(ox, i)]
            for c in range(3):
                s = sum(rgb[((y0 + iy) * w + x0 + ix) * 3 + c] * wy * wx
                        for iy, wy in ys for ix, wx in xs)
                out.append((s + side * side // 2) // (side * side))
    return bytes(out)


def squaring():
    pic = picture(128, 128, 300)
    if cover.square(128, 128, pic) != (pic, None):
        fail("a 128x128 picture is not left as it is")
    big = picture(384, 256, 40)
    got, how = cover.square(384, 256, big)
    want = bytearray()
    for oy in range(128):
        for ox in range(128):
            s = (oy * 2 * 384 + ox * 2 + 64) * 3
            want.extend(big[s:s + 3])
    if got != bytes(want) or "every 2nd pixel" not in how:
        fail("384x256 is not its centre 256x256 every 2nd pixel (%s)" % how)
    for w, h in ((320, 240), (160, 120), (200, 200), (50, 70)):
        pic = picture(w, h, 64)
        got, how = cover.square(w, h, pic)
        if got != area_average(w, h, pic):
            fail("%dx%d does not area-average as SPEC.md 3.6 says (%s)" % (w, h, how))
    ok("square: as it is, every k-th pixel, and the area average, against the slow way")


def vector(name):
    with open(os.path.join(VECTORS, name), "rb") as f:
        return f.read()


def lua_cart(tmp, name, canvas):
    cart = os.path.join(tmp, name + ".moy")
    os.makedirs(cart)
    with open(os.path.join(cart, "manifest.json"), "w") as f:
        json.dump({"format": "moy-1", "title": name, "canvas": canvas}, f)
    with open(os.path.join(cart, "main.lua"), "w") as f:
        f.write("function _draw()\n  cls(1)\n"
                "  for i = 0, 63 do rect(i * 5, i * 3, 40, 30, i) end\n"
                "  circ(64, 64, 50, 9) print('cover', 4, 4, 7)\nend\n")
    return cart


def cli(tmp):
    before = len(FAILS)
    cart = lua_cart(tmp, "shelf", "320x240")
    with open(os.path.join(cart, "cover.png"), "wb") as f:
        f.write(vector("rgba.png"))
    r = subprocess.run([sys.executable, MOY, "check", cart], capture_output=True, text=True)
    if r.returncode != 0 or "warn   cover" not in r.stdout:
        fail("moy check on a cover outside the profile: rc=%d %s" % (r.returncode, r.stdout))
    r = subprocess.run([sys.executable, MOY, "build", cart], capture_output=True, text=True)
    with open(os.path.join(cart, "cover.png"), "rb") as f:
        built = f.read()
    if r.returncode != 0 or cover.problem(built) or cover.read(built) != cover.read(
            cover.rewrite(vector("rgba.png"))[0]):
        fail("moy build on a Lua cart's RGBA cover: rc=%d %s" % (r.returncode, r.stdout + r.stderr))
    with open(os.path.join(cart, "cover.png"), "wb") as f:
        f.write(vector("size_512x512.png"))
    r = subprocess.run([sys.executable, MOY, "build", cart], capture_output=True, text=True)
    with open(os.path.join(cart, "cover.png"), "rb") as f:
        built = f.read()
    if r.returncode != 0 or "every 4th pixel" not in r.stdout or cover.problem(built):
        fail("moy build on a 512x512 cover: rc=%d %s" % (r.returncode, r.stdout + r.stderr))
    r = subprocess.run([sys.executable, MOY, "check", cart], capture_output=True, text=True)
    if r.returncode != 0 or "warn" in r.stdout:
        fail("moy check after moy build: %s" % r.stdout)

    sys.path.insert(0, ROOT)
    import moy
    os.remove(os.path.join(cart, "cover.png"))
    watch = moy._CoverWatch(cart)
    watch.poll()
    stored = vector("rgb_stored.png")
    with open(os.path.join(cart, "cover.png"), "wb") as f:
        f.write(stored)
    watch.poll()
    with open(os.path.join(cart, "cover.png"), "rb") as f:
        got = f.read()
    if len(got) >= len(stored) or cover.read(got) != cover.read(stored):
        fail("moy play's watcher left F7's cover at %d bytes" % len(got))
    if len(FAILS) == before:
        ok("moy check warns, moy build rewrites (a Lua cart's too), moy play recompresses "
           "F7's")


def player(tmp):
    if not os.path.isfile(PLAYER):
        print("  skip moy-play is not built (make play): F7's writer is not checked")
        return
    import wat
    carts = [(lua_cart(tmp, "c" + c, c), c) for c in ("320x240", "160x120", "128x128")]
    wasm = os.path.join(tmp, "verbs.moy")
    wat.build_cart(os.path.join(ROOT, "conformance", "wasm", "verbs.moy"), wasm)
    carts.append((wasm, "320x240"))
    before = len(FAILS)
    for cart, canvas in carts:
        w, h = (int(v) for v in canvas.split("x"))
        raw_path, png_path = os.path.join(tmp, "frame.bin"), os.path.join(tmp, "cover.png")
        a = subprocess.run([PLAYER, cart, "--dump", raw_path], capture_output=True, text=True)
        b = subprocess.run([PLAYER, cart, "--dump", png_path, "--cover"],
                           capture_output=True, text=True)
        if a.returncode or b.returncode:
            fail("moy-play --dump on %s: %s %s" % (cart, a.stderr, b.stderr))
            continue
        with open(raw_path, "rb") as f:
            raw = f.read()
        if cart == wasm:
            rgb = bytearray()
            for i in range(0, len(raw), 2):
                v = raw[i] | raw[i + 1] << 8
                r, g, bl = v >> 11, (v >> 5) & 63, v & 31
                rgb.extend(((r << 3) | (r >> 2), (g << 2) | (g >> 4), (bl << 3) | (bl >> 2)))
        else:
            rgb = b"".join(bytes(palette.MOY64[v]) for v in raw)
        want, how = cover.square(w, h, bytes(rgb))
        with open(png_path, "rb") as f:
            data = f.read()
        why = cover.problem(data)
        if why or cover.read(data) != want:
            fail("moy-play's cover of %s is not moycore's (%s)" % (cart, why))
        elif how and how.split(": ", 1)[1] not in b.stderr:
            fail("moy-play said %r; moycore says %r" % (b.stderr.strip(), how))
    if len(FAILS) == before:
        ok("moy-play --dump --cover is moycore's squaring at 320x240, 160x120, 128x128 "
           "and for a compiled cart, in the profile")


def main():
    print("covers:")
    vectors()
    writer()
    squaring()
    tmp = tempfile.mkdtemp(prefix="cover_test.")
    try:
        cli(tmp)
        player(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if FAILS:
        print("cover_test: %d failure(s)" % len(FAILS))
        return 1
    print("cover_test: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
