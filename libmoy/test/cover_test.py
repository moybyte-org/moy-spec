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

Run by `make cover-test`.
"""
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
VECTORS = os.path.join(ROOT, "conformance", "covers")
sys.path.insert(0, ROOT)

from moycore import cover                     # noqa: E402

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


def main():
    print("covers:")
    vectors()
    writer()
    squaring()
    if FAILS:
        print("cover_test: %d failure(s)" % len(FAILS))
        return 1
    print("cover_test: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
