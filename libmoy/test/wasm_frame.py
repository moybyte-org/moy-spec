#!/usr/bin/env python3
"""The frame hello.moy draws, rendered without libmoy, held against libmoy's.

    python3 test/wasm_frame.py build/wasm/hello.bin

build/wasm_test writes the frame the wasm binding produced -- RGB565,
little-endian, the golden form proposals/wasm-runtime.md pins for this
binding. This renders the same frame from the proposal's rules and moycore's
raster, which generates the suite's goldens: the blit's 256-entry palette
applied by hand, then the three verbs hello's _draw issues drawn by moycore
over it. The two must agree byte for byte, and their CRC32s are printed so a
failure says which side moved. Run by `make wasm-test`.
"""
import os
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))

import moycore                       # noqa: E402
from moycore import palette          # noqa: E402

W, H = 320, 240
UNDRAWN = 0xFF                       # no palette index is 255


def rgb565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def expected():
    # hello's _draw: frame[y * 320 + x] = (x + y) mod 256, blitted through the
    # palette _init wrote -- entry i is (i, 255 - i, 2i mod 256).
    pal = [rgb565(i, 255 - i, (2 * i) & 255) for i in range(256)]
    words = [pal[(i % W + i // W) & 255] for i in range(W * H)]

    # ...then rect, circ and print over it, which moycore draws onto a canvas
    # that starts out holding nothing any verb writes.
    c = moycore.Canvas(W, H)
    c.buf[:] = bytes((UNDRAWN,)) * (W * H)
    c.rect(10, 10, 50, 30, 8)
    c.circ(160, 120, 20, 12)
    c.print("HELLO", 100, 200, 7)
    table = [rgb565(*palette.MOY64[i]) for i in range(64)]
    for i, v in enumerate(c.buf):
        if v != UNDRAWN:
            words[i] = table[v]

    out = bytearray(W * H * 2)
    for i, v in enumerate(words):
        out[2 * i] = v & 0xFF
        out[2 * i + 1] = v >> 8
    return bytes(out)


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: wasm_frame.py <frame.bin>")
    with open(sys.argv[1], "rb") as f:
        got = f.read()
    want = expected()
    print("wasm frame: libmoy %08x, moycore %08x"
          % (zlib.crc32(got) & 0xFFFFFFFF, zlib.crc32(want) & 0xFFFFFFFF))
    if got != want:
        diff = sum(1 for i in range(0, min(len(got), len(want)), 2)
                   if got[i:i + 2] != want[i:i + 2])
        sys.exit("wasm frame: %d pixels differ (%d bytes against %d)"
                 % (diff, len(got), len(want)))
    print("wasm frame: the binding's frame is the one the proposal's rules draw")


if __name__ == "__main__":
    main()
