"""Build the cover vectors: PNG files a host's cover reader must accept or
ignore (SPEC.md 3.6), and expected.json saying which.

    python3 conformance/covers/build.py            # rewrite the vectors
    python3 conformance/covers/build.py --check    # expected.json is what this
                                                   # script would write

Each file is written here by hand -- its chunks, its filters, its zlib stream --
rather than by moycore's encoder, so a vector is exactly the case its name
says and does not change when the encoder learns a better trick. expected.json
gives each file's verdict, "cover" or "ignored", and for a cover the sha256 of
its pixels as R, G, B bytes, row-major from the top-left: that hash is taken
from the picture this script drew, not from any decoder's output.

The PNG bytes depend on the zlib that compressed them, so a rebuild on another
machine may differ byte for byte while saying the same thing; --check compares
expected.json only, and libmoy/test/cover_test.py holds the committed files to
it.
"""

import hashlib
import json
import os
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
SIZE = 128
MAX_BYTES = 65536


# --- writing a PNG by hand ---------------------------------------------------

def chunk(tag, body):
    return (struct.pack(">I", len(body)) + tag + body
            + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF))


def ihdr(w, h, depth, ctype, interlace=0):
    return chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, depth, ctype, 0, 0, interlace))


def plte(palette):
    return chunk(b"PLTE", b"".join(bytes(c) for c in palette))


def filter_row(ft, line, prev, bpp):
    out = bytearray(len(line))
    for i in range(len(line)):
        a = line[i - bpp] if i >= bpp else 0
        b = prev[i]
        c = prev[i - bpp] if i >= bpp else 0
        if ft == 0:
            p = 0
        elif ft == 1:
            p = a
        elif ft == 2:
            p = b
        elif ft == 3:
            p = (a + b) >> 1
        else:
            q = a + b - c
            pa, pb, pc = abs(q - a), abs(q - b), abs(q - c)
            p = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
        out[i] = (line[i] - p) & 0xFF
    return out


def scanlines(rows, bpp, filters):
    """Filtered image data. `filters` gives row y the filter filters[y % n]."""
    out = bytearray()
    prev = bytearray(len(rows[0]))
    for y, line in enumerate(rows):
        ft = filters[y % len(filters)]
        out.append(ft)
        out.extend(filter_row(ft, line, prev, bpp))
        prev = line
    return bytes(out)


def stored(raw):
    """A zlib stream of stored (uncompressed) deflate blocks."""
    out = bytearray(b"\x78\x01")
    for at in range(0, len(raw), 65535):
        block = raw[at:at + 65535]
        out.append(1 if at + 65535 >= len(raw) else 0)
        out.extend(struct.pack("<HH", len(block), len(block) ^ 0xFFFF))
        out.extend(block)
    out.extend(struct.pack(">I", zlib.adler32(raw) & 0xFFFFFFFF))
    return bytes(out)


def png(head, idat, before=(), after=()):
    return (b"\x89PNG\r\n\x1a\n" + head + b"".join(before)
            + b"".join(chunk(b"IDAT", part) for part in idat)
            + b"".join(after) + chunk(b"IEND", b""))


# --- the pictures ------------------------------------------------------------

def lcg(seed):
    state = [seed & 0xFFFFFFFF]

    def nxt():
        state[0] = (state[0] * 1664525 + 1013904223) & 0xFFFFFFFF
        return state[0] >> 24
    return nxt


def rgb_picture(w, h, seed=1):
    """Gradients, a checker and scattered noise, so every filter's predictor
    sees non-zero neighbours of every kind."""
    rnd = lcg(seed)
    out = bytearray()
    for y in range(h):
        for x in range(w):
            r = (x * 2 + y) & 255
            g = (y * 2 + (x >> 2)) & 255
            b = 200 if ((x >> 4) ^ (y >> 4)) & 1 else 40
            if (x * 7 + y * 13) % 29 == 0:
                r, g, b = rnd(), rnd(), rnd()
            out.extend((r, g, b))
    return bytes(out)


def palette_of(n, seed=2):
    rnd = lcg(seed)
    return [(rnd(), rnd(), rnd()) for _ in range(n)]


def index_picture(w, h, n, seed=3):
    rnd = lcg(seed)
    out = bytearray()
    for y in range(h):
        for x in range(w):
            v = ((x >> 3) + (y >> 3) * 3) % n
            if (x + y * 5) % 23 == 0:
                v = rnd() % n
            out.append(v)
    return bytes(out)


def rows_of(data, w, bpp):
    stride = w * bpp
    return [bytearray(data[i:i + stride]) for i in range(0, len(data), stride)]


def expand(indices, palette):
    return b"".join(bytes(palette[v]) for v in indices)


def sha(data):
    return hashlib.sha256(data).hexdigest()


# --- the vectors -------------------------------------------------------------

def rgb_file(filters, w=SIZE, h=SIZE, seed=1, stream=None, **kw):
    pic = rgb_picture(w, h, seed)
    raw = scanlines(rows_of(pic, w, 3), 3, filters)
    body = (stream or (lambda r: zlib.compress(r, 9)))(raw)
    return png(ihdr(w, h, 8, 2), [body], **kw), pic


def indexed_file(filters, n=16, w=SIZE, h=SIZE, seed=3, **kw):
    pal = palette_of(n)
    pic = index_picture(w, h, n, seed)
    raw = scanlines(rows_of(pic, w, 1), 1, filters)
    head = ihdr(w, h, 8, 3) + plte(pal)
    return png(head, [zlib.compress(raw, 9)], **kw), expand(pic, pal)


def padded_to(total, make):
    """The file `make(pad)` gives with an ancillary chunk of `pad` bytes,
    sized so the whole file is exactly `total` bytes."""
    data, pic = make(b"")
    pad = total - len(data)
    if pad < 0:
        raise SystemExit("cannot pad a %d-byte file to %d" % (len(data), total))
    data, pic2 = make(b"\0" * pad)
    assert len(data) == total and pic2 == pic
    return data, pic


def text(key, value):
    return chunk(b"tEXt", key + b"\0" + value)


def vectors():
    """[(name, bytes, picture or None, note)] -- picture None means ignored."""
    out = []

    def cover(name, made, note):
        out.append((name, made[0], made[1], note))

    def ignored(name, data, note):
        out.append((name, data, None, note))

    for ft in range(5):
        cover("rgb_filter%d" % ft, rgb_file([ft]), "colour type 2, every row filter %d" % ft)
        cover("indexed_filter%d" % ft, indexed_file([ft]),
              "colour type 3, 16 entries, every row filter %d" % ft)
    cover("rgb_filters_mixed", rgb_file([0, 1, 2, 3, 4, 4, 3, 2, 1]),
          "colour type 2, the five filters mixed row by row")
    cover("indexed_filters_mixed", indexed_file([4, 0, 3, 1, 2]),
          "colour type 3, the five filters mixed row by row")
    cover("palette_1", indexed_file([0, 2], n=1), "a one-entry PLTE: every pixel index 0")
    cover("palette_256", indexed_file([1, 4], n=256),
          "a 256-entry PLTE, every entry used")
    cover("rgb_stored", rgb_file([0], stream=stored),
          "colour type 2 in stored deflate blocks: no compression at all, "
          "and still under the size limit")

    def split(raw):
        z = zlib.compress(raw, 9)
        return [z[:1], b"", z[1:700], z[700:]]
    pic = rgb_picture(SIZE, SIZE, 4)
    data = png(ihdr(SIZE, SIZE, 8, 2),
               split(scanlines(rows_of(pic, SIZE, 3), 3, [1, 2])),
               before=[text(b"Title", b"before the image"), chunk(b"gAMA", struct.pack(">I", 45455)),
                       chunk(b"pHYs", struct.pack(">IIB", 2835, 2835, 1)),
                       chunk(b"moYb", b"a private ancillary chunk")],
               after=[text(b"Comment", b"after the image"),
                      chunk(b"tIME", struct.pack(">HBBBBB", 2026, 10, 2, 0, 0, 0))])
    cover("ancillary_and_split_idat", (data, pic),
          "ancillary chunks before and after the image data, and the zlib stream "
          "split over four IDAT chunks, one of them empty")
    pal = palette_of(8)
    pic = rgb_picture(SIZE, SIZE, 5)
    data = png(ihdr(SIZE, SIZE, 8, 2) + plte(pal),
               [zlib.compress(scanlines(rows_of(pic, SIZE, 3), 3, [4]), 9)])
    cover("rgb_with_suggested_plte", (data, pic),
          "colour type 2 carrying a PLTE, which PNG allows as a suggestion and a "
          "reader skips")
    cover("size_limit_exact",
          padded_to(MAX_BYTES, lambda pad: rgb_file([0, 4], seed=6,
                                                     after=[chunk(b"zzPd", pad)])),
          "exactly %d bytes" % MAX_BYTES)

    ignored("size_limit_plus_one",
            padded_to(MAX_BYTES + 1, lambda pad: rgb_file([0, 4], seed=6,
                                                           after=[chunk(b"zzPd", pad)]))[0],
            "%d bytes, one over" % (MAX_BYTES + 1))
    ignored("size_127x128", rgb_file([1], w=127)[0], "127 wide")
    ignored("size_128x129", rgb_file([1], h=129)[0], "129 high")
    ignored("size_1x1", rgb_file([0], w=1, h=1)[0], "1x1")
    ignored("size_512x512", indexed_file([0], n=4, w=512, h=512)[0], "512x512")

    pic = rgb_picture(SIZE, SIZE, 7)
    raw = bytearray()
    for x0, y0, dx, dy in ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
                           (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2)):
        sub = [bytearray(b"".join(pic[(y * SIZE + x) * 3:(y * SIZE + x) * 3 + 3]
                                  for x in range(x0, SIZE, dx)))
               for y in range(y0, SIZE, dy)]
        raw.extend(scanlines(sub, 3, [1]))
    ignored("interlaced", png(ihdr(SIZE, SIZE, 8, 2, interlace=1),
                              [zlib.compress(bytes(raw), 9)]), "Adam7 interlaced")
    pic16 = b"".join(bytes((v, v)) for v in rgb_picture(SIZE, SIZE, 8))
    ignored("depth16", png(ihdr(SIZE, SIZE, 16, 2),
                           [zlib.compress(scanlines(rows_of(pic16, SIZE, 6), 6, [1]), 9)]),
            "colour type 2 at bit depth 16")
    pic = rgb_picture(SIZE, SIZE, 9)
    rgba = b"".join(pic[i:i + 3] + b"\xff" for i in range(0, len(pic), 3))
    ignored("rgba", png(ihdr(SIZE, SIZE, 8, 6),
                        [zlib.compress(scanlines(rows_of(rgba, SIZE, 4), 4, [1]), 9)]),
            "colour type 6 (RGBA), every pixel opaque")
    ignored("trns", _with_trns(), "colour type 3 with a tRNS chunk")
    grey = bytes((x + y) & 255 for y in range(SIZE) for x in range(SIZE))
    ignored("greyscale", png(ihdr(SIZE, SIZE, 8, 0),
                             [zlib.compress(scanlines(rows_of(grey, SIZE, 1), 1, [0]), 9)]),
            "colour type 0 (greyscale)")
    four = bytes(((x >> 3) & 15) << 4 | ((x >> 3) + 1) & 15 for y in range(SIZE)
                 for x in range(0, SIZE, 2))
    ignored("indexed_depth4", png(ihdr(SIZE, SIZE, 4, 3) + plte(palette_of(16)),
                                  [zlib.compress(scanlines(rows_of(four, SIZE // 2, 1), 1,
                                                           [0]), 9)]),
            "colour type 3 at bit depth 4")

    pic = rgb_picture(SIZE, SIZE, 10)
    z = zlib.compress(scanlines(rows_of(pic, SIZE, 3), 3, [1]), 9)
    ignored("truncated_idat", png(ihdr(SIZE, SIZE, 8, 2), [z[:len(z) // 2]]),
            "the zlib stream cut in half; every chunk is well formed")
    bad = b"\x78\xda" + bytes((0x07,)) + z[3:]
    ignored("bad_zlib", png(ihdr(SIZE, SIZE, 8, 2), [bad]),
            "the first deflate block has the reserved block type 3")
    raw = bytearray(scanlines(rows_of(pic, SIZE, 3), 3, [1]))
    raw[40 * (1 + SIZE * 3)] = 5
    ignored("bad_filter", png(ihdr(SIZE, SIZE, 8, 2), [zlib.compress(bytes(raw), 9)]),
            "row 40 names filter type 5")
    pal = palette_of(16)
    pic = bytearray(index_picture(SIZE, SIZE, 16))
    pic[SIZE * 64 + 64] = 16
    ignored("index_past_plte", png(ihdr(SIZE, SIZE, 8, 3) + plte(pal),
                                   [zlib.compress(scanlines(rows_of(pic, SIZE, 1), 1, [0]),
                                                  9)]),
            "one pixel names entry 16 of a 16-entry PLTE")
    pic = index_picture(SIZE, SIZE, 16)
    ignored("indexed_no_plte", png(ihdr(SIZE, SIZE, 8, 3),
                                   [zlib.compress(scanlines(rows_of(pic, SIZE, 1), 1, [0]),
                                                  9)]),
            "colour type 3 with no PLTE")
    ignored("not_png", b"GIF89a" + b"\0" * 64, "not a PNG at all")
    return out


def _with_trns():
    pal = palette_of(16)
    pic = index_picture(SIZE, SIZE, 16)
    head = ihdr(SIZE, SIZE, 8, 3) + plte(pal) + chunk(b"tRNS", b"\x00")
    return png(head, [zlib.compress(scanlines(rows_of(pic, SIZE, 1), 1, [0]), 9)])


def expected(made):
    out = {
        "_": "SPEC.md 3.6's cover profile, as files. A host's reader takes each "
             "file's bytes and either shows a cover or ignores the file; for a "
             "cover, rgb888_sha256 is the sha256 of its 128x128 pixels as R, G, B "
             "bytes, row-major from the top-left. Regenerate with "
             "conformance/covers/build.py.",
        "vectors": [],
    }
    for name, data, pic, note in made:
        entry = {"file": name + ".png", "verdict": "cover" if pic else "ignored",
                 "bytes": len(data), "note": note}
        if pic:
            assert len(pic) == SIZE * SIZE * 3
            entry["rgb888_sha256"] = sha(pic)
        out["vectors"].append(entry)
    return out


def main(argv):
    made = vectors()
    want = expected(made)
    path = os.path.join(HERE, "expected.json")
    if "--check" in argv:
        with open(path, encoding="utf-8") as f:
            have = json.load(f)
        strip = lambda e: dict((k, v) for k, v in e.items() if k != "bytes")
        if [strip(e) for e in have["vectors"]] != [strip(e) for e in want["vectors"]]:
            print("covers: expected.json is not what build.py writes -- rerun it")
            return 1
        print("covers: expected.json is what build.py writes (%d vectors)"
              % len(want["vectors"]))
        return 0
    for name in os.listdir(HERE):
        if name.endswith(".png"):
            os.remove(os.path.join(HERE, name))
    for name, data, _pic, _note in made:
        with open(os.path.join(HERE, name + ".png"), "wb") as f:
            f.write(data)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(want, f, indent=1)
        f.write("\n")
    print("covers: %d vectors -> %s" % (len(made), os.path.relpath(HERE)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
