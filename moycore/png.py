"""A minimal PNG codec (stdlib zlib only).

moy has no dependencies and is not about to grow one for image I/O. This is
enough PNG for the two jobs the project actually has:

  * WRITE golden frames and sheet exports (indexed PNG, so a golden is one byte
    per pixel and a diff is meaningful rather than a JPEG-ish smear).
  * READ a sheet back from whatever the artist drew it in. Aseprite, GIMP,
    Piskel and Photoshop all export 8-bit palette or RGB/RGBA PNGs; those are
    supported. Interlaced and 16-bit-per-channel are not, and say so.
"""

import struct
import zlib


class PngError(Exception):
    pass


def _chunk(tag, data):
    out = struct.pack(">I", len(data)) + tag + data
    return out + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def write_indexed(path, w, h, indices, palette):
    """An 8-bit palette PNG: one byte per pixel plus a PLTE table.

    This is the golden-frame format. Keeping goldens indexed rather than RGB
    means a frame file IS the console's framebuffer -- byte-comparable, and a
    palette change shows up as a palette change instead of rewriting every
    pixel in the diff."""
    plte = bytearray()
    for rgb in palette:
        plte.append(rgb[0]); plte.append(rgb[1]); plte.append(rgb[2])
    raw = bytearray()
    for y in range(h):
        raw.append(0)                                  # filter: none
        raw.extend(indices[y * w:(y + 1) * w])
    body = (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 3, 0, 0, 0))
            + _chunk(b"PLTE", bytes(plte))
            + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + _chunk(b"IEND", b""))
    f = open(path, "wb")
    try:
        f.write(body)
    finally:
        f.close()
    return len(body)


def _unfilter(raw, w, h, bpp):
    """Undo the five PNG scanline filters. Straight from the spec's own
    pseudocode -- there is no clever version of this."""
    stride = w * bpp
    out = bytearray(stride * h)
    pos = 0
    for y in range(h):
        ft = raw[pos]; pos += 1
        line = raw[pos:pos + stride]; pos += stride
        base = y * stride
        prev = base - stride
        if ft == 0:
            out[base:base + stride] = line
        elif ft == 1:
            for i in range(stride):
                a = out[base + i - bpp] if i >= bpp else 0
                out[base + i] = (line[i] + a) & 0xFF
        elif ft == 2:
            for i in range(stride):
                b = out[prev + i] if y else 0
                out[base + i] = (line[i] + b) & 0xFF
        elif ft == 3:
            for i in range(stride):
                a = out[base + i - bpp] if i >= bpp else 0
                b = out[prev + i] if y else 0
                out[base + i] = (line[i] + ((a + b) >> 1)) & 0xFF
        elif ft == 4:
            for i in range(stride):
                a = out[base + i - bpp] if i >= bpp else 0
                b = out[prev + i] if y else 0
                c = out[prev + i - bpp] if (y and i >= bpp) else 0
                p = a + b - c
                pa = abs(p - a); pb = abs(p - b); pc = abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                out[base + i] = (line[i] + pr) & 0xFF
        else:
            raise PngError("unknown scanline filter %d" % ft)
    return out


def read_rgb(path):
    """(w, h, [(r, g, b), ...]) for an 8-bit non-interlaced PNG.

    Accepts greyscale, RGB, RGBA, palette and their +alpha forms; alpha is
    dropped (a sheet is indexed, so transparency is a palette index, not a
    channel -- see SPEC.md 7.1's colorkey)."""
    f = open(path, "rb")
    try:
        data = f.read()
    finally:
        f.close()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise PngError("%s is not a PNG" % path)
    pos = 8
    w = h = depth = ctype = None
    plte = None
    idat = bytearray()
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if tag == b"IHDR":
            w, h, depth, ctype, _comp, _filt, interlace = struct.unpack(">IIBBBBB", body)
            if depth != 8:
                raise PngError("only 8-bit PNGs are supported (this one is %d-bit)" % depth)
            if interlace:
                raise PngError("interlaced PNGs are not supported; re-export without Adam7")
        elif tag == b"PLTE":
            plte = body
        elif tag == b"IDAT":
            idat.extend(body)
        elif tag == b"IEND":
            break
    if w is None:
        raise PngError("%s has no IHDR" % path)
    bpp = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(ctype)
    if bpp is None:
        raise PngError("unsupported PNG colour type %d" % ctype)
    raw = _unfilter(zlib.decompress(bytes(idat)), w, h, bpp)
    px = []
    for i in range(w * h):
        o = i * bpp
        if ctype == 0:
            v = raw[o]; px.append((v, v, v))
        elif ctype == 4:
            v = raw[o]; px.append((v, v, v))
        elif ctype == 2 or ctype == 6:
            px.append((raw[o], raw[o + 1], raw[o + 2]))
        else:
            if plte is None:
                raise PngError("palette PNG with no PLTE chunk")
            j = raw[o] * 3
            px.append((plte[j], plte[j + 1], plte[j + 2]))
    return w, h, px


def nearest_index(rgb, palette, limit=None):
    """The palette index closest to `rgb` by squared RGB distance.

    Used when importing art that was not drawn against the moy palette. Plain
    euclidean rather than perceptual: the common case is an EXACT match (an
    artist working from palette.json), where any metric agrees, and a fancier
    one would only change which wrong colour you get when there is no match."""
    n = len(palette) if limit is None else min(limit, len(palette))
    best = 0
    best_d = None
    for i in range(n):
        pr, pg, pb = palette[i]
        d = (pr - rgb[0]) ** 2 + (pg - rgb[1]) ** 2 + (pb - rgb[2]) ** 2
        if best_d is None or d < best_d:
            best = i
            best_d = d
            if d == 0:
                break
    return best
