#!/usr/bin/env python3
"""The importer's cover: a PICO-8 cart's label becomes cover.png (SPEC.md 3.6).

    python3 libmoy/test/p8_label_check.py        (`make -C libmoy p8-test`)

  * THE REGION. A .p8.png's label is the 128x128 at (16, 24) of the 160x205
    cartridge picture. A cartridge is built here whose label is a known
    pattern and whose one-pixel ring around it is NOT black, so a region one
    pixel off reads the ring into the label's edge and fails. Then every real
    cartridge to hand -- the conformance corpus (MOY_P8_CORPUS, else
    ~/.cache/moy/p8) and 15133.p8.png, Celeste Classic, in the repository root
    when it was downloaded there for `moy demo` -- is held to the template that
    region assumes: the one-pixel ring around the label all the cartridge's frame
    colour, which no label pixel is, and the cartridge's grey two pixels out;
    every label pixel one of PICO-8's 32 colours on its high six bits, or the
    green PICO-8 used before it changed it.
  * THE FILE. The .p8 `__label__` and the .p8.png picture both port to the
    same cover.png: indexed, PICO-8's 32 colours as its PLTE, pixel for pixel
    the label. A cart with no label, or an all-black one, gets no cover.
  * THE FALLBACKS a console's MicroPython takes, where zlib cannot compress:
    stored deflate blocks, and a CRC by hand.
"""
import glob
import os
import struct
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

import p8_import                                              # noqa: E402
import p8_lua_port                                            # noqa: E402
from moycore import cover                                     # noqa: E402

FAIL = []
PAL = [(int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)) for c in p8_import.P8_COLOURS]
X0, Y0, N = p8_import.LABEL_X, p8_import.LABEL_Y, p8_import.LABEL_SIZE


def pattern():
    return ["".join(p8_import.LABEL_DIGITS[(x * 3 + y * 5 + (x * y) % 7) % 32]
                    for x in range(N)) for y in range(N)]


def expand(lines):
    return b"".join(bytes(PAL[p8_import.LABEL_DIGITS.index(c)]) for line in lines for c in line)


def cartridge(lines, code=b"function _draw() cls() end\0"):
    """A 160x205 .p8.png: the ROM in every pixel's low two bits per channel,
    `lines` drawn as the label, a red ring around it, grey outside."""
    w, h = 160, 205
    rom = bytearray(w * h)
    rom[0x4300:0x4300 + len(code)] = code
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        for x in range(w):
            if X0 <= x < X0 + N and Y0 <= y < Y0 + N:
                r, g, b = PAL[p8_import.LABEL_DIGITS.index(lines[y - Y0][x - X0])]
            elif X0 - 1 <= x <= X0 + N and Y0 - 1 <= y <= Y0 + N:
                r, g, b = PAL[8]
            else:
                r, g, b = 100, 100, 100
            v = rom[y * w + x]
            raw.extend(((r & 0xFC) | (v >> 4 & 3), (g & 0xFC) | (v >> 2 & 3),
                        (b & 0xFC) | (v & 3), 0xFC | (v >> 6)))

    def chunk(tag, body):
        return struct.pack(">I", len(body)) + tag + body + \
            struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b""))


def port(tmp, name, data):
    src = os.path.join(tmp, name)
    with open(src, "wb") as f:
        f.write(data)
    out = os.path.join(tmp, name + ".moy")
    p8_lua_port.port(src, out, title=name, force=True)
    path = os.path.join(out, "cover.png")
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        return f.read()


def region_and_file(tmp):
    lines = pattern()
    png = cartridge(lines)
    sections = p8_import.read_p8(_write(tmp, "pattern.p8.png", png))
    if sections.get("label") != lines:
        FAIL.append(".p8.png: the label read is not the label drawn at (%d, %d)" % (X0, Y0))
    want = expand(lines)
    for name, data in (("pattern.p8.png", png),
                       ("pattern.p8", ("pico-8 cartridge // http://www.pico-8.com\nversion 41\n"
                                       "__lua__\nfunction _draw() cls() end\n__label__\n"
                                       + "\n".join(lines) + "\n").encode())):
        got = port(tmp, name, data)
        if got is None:
            FAIL.append("%s: no cover.png" % name)
            continue
        if cover.problem(got) or got[25] != 3 or cover.read(got) != want:
            FAIL.append("%s: cover.png is not the label (%s)" % (name, cover.problem(got)))
        plte = got[got.index(b"PLTE") + 4:got.index(b"PLTE") + 4 + 96]
        if plte != b"".join(bytes(c) for c in PAL):
            FAIL.append("%s: the PLTE is not PICO-8's 32 colours" % name)
    for name, body in (("nolabel.p8", ""), ("black.p8", "__label__\n" + "\n".join(["0" * N] * N))):
        text = ("pico-8 cartridge // http://www.pico-8.com\nversion 41\n__lua__\n"
                "function _draw() cls() end\n" + body + "\n")
        if port(tmp, name, text.encode()) is not None:
            FAIL.append("%s: a cart with no label got a cover" % name)
    if port(tmp, "black.p8.png", cartridge(["0" * N] * N)) is not None:
        FAIL.append("black.p8.png: an all-black label got a cover")


def _write(tmp, name, data):
    path = os.path.join(tmp, name)
    with open(path, "wb") as f:
        f.write(data)
    return path


def real_carts():
    corpus = os.environ.get("MOY_P8_CORPUS") or os.path.join(
        os.path.expanduser("~"), ".cache", "moy", "p8")
    paths = sorted(glob.glob(os.path.join(corpus, "*.p8.png")))
    celeste = os.path.join(ROOT, "15133.p8.png")
    if os.path.isfile(celeste):
        paths.append(celeste)
    if not paths:
        print("  (no PICO-8 cartridges to hand: the region is checked on the built one only)")
        return 0
    masked = set((r & 0xFC, g & 0xFC, b & 0xFC) for r, g, b in PAL)
    masked.add((0x00, 0xE4, 0x54))           # #00E756, PICO-8's green until 0.1.x
    frame = (0x00, 0x04, 0x08)               # the cartridge's near-black frame
    for path in paths:
        with open(path, "rb") as f:
            w, h, px = p8_import._png_scanlines(f.read())

        def at(x, y):
            o = (y * w + x) * 4
            return (px[o] & 0xFC, px[o + 1] & 0xFC, px[o + 2] & 0xFC)
        name = os.path.basename(path)
        if any(at(x, y) not in masked for y in range(Y0, Y0 + N) for x in range(X0, X0 + N)):
            FAIL.append("%s: a label pixel is not one of PICO-8's colours" % name)
        ring = [(x, y) for x in range(X0 - 1, X0 + N + 1) for y in (Y0 - 1, Y0 + N)] + \
               [(x, y) for y in range(Y0 - 1, Y0 + N + 1) for x in (X0 - 1, X0 + N)]
        if any(at(x, y) != frame for x, y in ring):
            FAIL.append("%s: the ring around (%d, %d) is not the frame" % (name, X0, Y0))
        outer = [(x, Y0 - 2) for x in range(X0 - 2, X0 + N + 2)]
        if any(at(x, y) in (frame, (0, 0, 0)) for x, y in outer):
            FAIL.append("%s: the cartridge's grey does not start two pixels out" % name)
    return len(paths)


def fallbacks():
    raw = bytes(range(256)) * 300
    if zlib.decompress(p8_import._zlib_stored(raw)) != raw:
        FAIL.append("_zlib_stored does not inflate back")
    for data in (b"", b"IEND", raw):
        if p8_import._crc32_by_hand(data) != zlib.crc32(data) & 0xFFFFFFFF:
            FAIL.append("_crc32_by_hand disagrees with zlib")


def main():
    tmp = tempfile.mkdtemp(prefix="p8_label.")
    region_and_file(tmp)
    seen = real_carts()
    fallbacks()
    if FAIL:
        for f in FAIL:
            print("  FAIL " + f)
        print("p8_label_check: %d failure(s)" % len(FAIL))
        return 1
    print("p8_label_check: the label is the 128x128 at (%d, %d)%s, and it ports as "
          "cover.png" % (X0, Y0, " in all %d real cartridges too" % seen if seen else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
