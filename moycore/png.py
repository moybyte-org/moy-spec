"""A minimal PNG codec (stdlib zlib only).

moy has no dependencies and is not about to grow one for image I/O. This is
enough PNG for the three jobs the project actually has:

  * WRITE golden frames and sheet exports (indexed PNG, so a golden is one byte
    per pixel and a diff is meaningful rather than a JPEG-ish smear).
  * READ a sheet back from whatever the artist drew it in. Aseprite, GIMP,
    Piskel and Photoshop all export 8-bit palette or RGB/RGBA PNGs; those are
    supported by `read_rgb`. Interlaced and 16-bit-per-channel are not, and say
    so.
  * COVERS (SPEC.md 3.6, moycore/cover.py): `decode` reads any PNG a paint
    program writes -- every colour type, bit depth and Adam7 -- so `moy build`
    can rewrite one into the profile, and `encode` writes the smallest PNG it
    can find for a picture.
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


# --- any PNG, decoded --------------------------------------------------------

SIGNATURE = b"\x89PNG\r\n\x1a\n"
CRITICAL = (b"IHDR", b"PLTE", b"IDAT", b"IEND")
_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
_DEPTHS = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
# Adam7: (x0, y0, dx, dy) for each of the seven passes.
_ADAM7 = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4),
          (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))


def chunks(data):
    """[(tag, body), ...] for a PNG's bytes, through IEND. CRCs are not
    checked. Raises PngError on a bad signature or a chunk that runs past the
    end of the data."""
    if data[:8] != SIGNATURE:
        raise PngError("not a PNG (bad signature)")
    out = []
    pos = 8
    while True:
        if pos + 8 > len(data):
            raise PngError("the file ends before IEND")
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        tag = bytes(data[pos + 4:pos + 8])
        if pos + 12 + length > len(data):
            raise PngError("the %s chunk runs past the end of the file"
                           % tag.decode("latin-1"))
        out.append((tag, bytes(data[pos + 8:pos + 8 + length])))
        pos += 12 + length
        if tag == b"IEND":
            return out


def _inflate(idat, want):
    """Exactly `want` bytes from a zlib stream, or PngError."""
    d = zlib.decompressobj()
    try:
        raw = d.decompress(idat, want + 1)
        raw += d.flush()
    except zlib.error as exc:
        raise PngError("the image data does not inflate: %s" % exc)
    if len(raw) < want:
        raise PngError("the image data is short: %d bytes of %d" % (len(raw), want))
    if len(raw) > want or not d.eof:
        raise PngError("the image data is not one complete zlib stream of %d bytes"
                       % want)
    return raw


def _samples(raw, w, h, depth, channels):
    """Unfiltered scanlines -> one int per sample, row-major."""
    bits = depth * channels
    stride = (w * bits + 7) // 8
    if bits >= 8:
        out = _unfilter(raw, w, h, bits // 8)
    else:
        out = _unfilter(raw, stride, h, 1)
    n = w * channels
    if depth == 8:
        return out
    if depth == 16:
        return [(out[i] << 8) | out[i + 1] for i in range(0, len(out), 2)]
    mask = (1 << depth) - 1
    vals = []
    for y in range(h):
        row = out[y * stride:(y + 1) * stride]
        for i in range(n):
            bit = i * depth
            vals.append((row[bit >> 3] >> (8 - depth - (bit & 7))) & mask)
    return vals


class Decoded(object):
    """A PNG, decoded. `rgb` is every pixel as 8-bit R, G, B with any alpha
    flattened onto black; `indices` and `palette` are the file's own when it is
    colour type 3 with no transparency (None otherwise); `ancillary` lists the
    tags of the chunks a decoder may skip."""

    def __init__(self, w, h, depth, ctype, interlace, rgb, indices, palette,
                 has_alpha, ancillary):
        self.w = w
        self.h = h
        self.depth = depth
        self.ctype = ctype
        self.interlace = interlace
        self.rgb = rgb
        self.indices = indices
        self.palette = palette
        self.has_alpha = has_alpha
        self.ancillary = ancillary


def decode(data):
    """Any valid PNG -> Decoded. Raises PngError naming what is wrong."""
    parts = chunks(data)
    if not parts or parts[0][0] != b"IHDR" or len(parts[0][1]) != 13:
        raise PngError("the first chunk is not a 13-byte IHDR")
    w, h, depth, ctype, comp, filt, interlace = struct.unpack(">IIBBBBB", parts[0][1])
    if w < 1 or h < 1:
        raise PngError("the image is %dx%d" % (w, h))
    if ctype not in _CHANNELS or depth not in _DEPTHS[ctype]:
        raise PngError("colour type %d at bit depth %d is not a PNG format"
                       % (ctype, depth))
    if comp or filt or interlace > 1:
        raise PngError("unknown compression, filter or interlace method")
    plte = trns = None
    idat = bytearray()
    ancillary = []
    for tag, body in parts[1:]:
        if tag == b"PLTE":
            if len(body) % 3 or not 3 <= len(body) <= 768:
                raise PngError("PLTE holds %d bytes, not 1-256 entries" % len(body))
            plte = body
        elif tag == b"IDAT":
            idat.extend(body)
        elif tag == b"tRNS":
            trns = body
            ancillary.append(tag)
        elif tag == b"IHDR" or not (tag[0] & 0x20):
            if tag not in CRITICAL:
                raise PngError("unknown critical chunk %s" % tag.decode("latin-1"))
        else:
            ancillary.append(tag)
    if ctype == 3 and plte is None:
        raise PngError("a palette image with no PLTE")
    channels = _CHANNELS[ctype]
    bits = depth * channels
    if interlace:
        passes = []
        want = 0
        for x0, y0, dx, dy in _ADAM7:
            pw, ph = (w - x0 + dx - 1) // dx, (h - y0 + dy - 1) // dy
            if pw and ph:
                passes.append((x0, y0, dx, dy, pw, ph))
                want += ph * (1 + (pw * bits + 7) // 8)
        raw = _inflate(bytes(idat), want)
        samples = [0] * (w * h * channels)
        pos = 0
        for x0, y0, dx, dy, pw, ph in passes:
            size = ph * (1 + (pw * bits + 7) // 8)
            sub = _samples(raw[pos:pos + size], pw, ph, depth, channels)
            pos += size
            for py in range(ph):
                for px in range(pw):
                    s = (py * pw + px) * channels
                    d = ((y0 + py * dy) * w + x0 + px * dx) * channels
                    samples[d:d + channels] = sub[s:s + channels]
    else:
        raw = _inflate(bytes(idat), h * (1 + (w * bits + 7) // 8))
        samples = _samples(raw, w, h, depth, channels)
    return _to_rgb(w, h, depth, ctype, interlace, samples, plte, trns, ancillary)


def _to_rgb(w, h, depth, ctype, interlace, samples, plte, trns, ancillary):
    top = (1 << depth) - 1
    n = w * h
    rgb = bytearray(n * 3)
    alpha = [255] * n
    if ctype == 3:
        entries = len(plte) // 3
        ta = bytearray(trns or b"")[:entries]
        for i in range(n):
            v = samples[i]
            if v >= entries:
                raise PngError("pixel %d names palette entry %d of %d" % (i, v, entries))
            rgb[i * 3:i * 3 + 3] = plte[v * 3:v * 3 + 3]
            if v < len(ta):
                alpha[i] = ta[v]
        has_alpha = any(a != 255 for a in ta)
        palette = None if has_alpha else [tuple(plte[j * 3:j * 3 + 3])
                                          for j in range(entries)]
        indices = None if has_alpha else bytes(samples)
    else:
        channels = _CHANNELS[ctype]
        key = None
        if trns is not None and ctype in (0, 2):
            key = struct.unpack(">%dH" % (len(trns) // 2), trns)
        for i in range(n):
            s = samples[i * channels:(i + 1) * channels]
            if key is not None and tuple(s) == key:
                alpha[i] = 0
            if ctype in (0, 4):
                v = (s[0] * 255 + top // 2) // top
                rgb[i * 3] = rgb[i * 3 + 1] = rgb[i * 3 + 2] = v
            else:
                for c in range(3):
                    rgb[i * 3 + c] = (s[c] * 255 + top // 2) // top
            if ctype in (4, 6):
                alpha[i] = (s[-1] * 255 + top // 2) // top
        has_alpha = any(a != 255 for a in alpha)
        palette = indices = None
    if has_alpha:
        for i in range(n):
            a = alpha[i]
            if a != 255:
                for c in range(3):
                    rgb[i * 3 + c] = (rgb[i * 3 + c] * a + 127) // 255
    return Decoded(w, h, depth, ctype, interlace, bytes(rgb), indices, palette,
                   has_alpha, ancillary)


# --- the smallest PNG for a picture ------------------------------------------

def _filter_row(ft, line, prev, bpp):
    """One scanline under filter `ft`, as the bytes that follow its filter
    byte. `prev` is the unfiltered row above (zeros for the first)."""
    out = bytearray(len(line))
    for i in range(len(line)):
        a = line[i - bpp] if i >= bpp else 0
        b = prev[i]
        if ft == 0:
            p = 0
        elif ft == 1:
            p = a
        elif ft == 2:
            p = b
        elif ft == 3:
            p = (a + b) >> 1
        else:
            c = prev[i - bpp] if i >= bpp else 0
            q = a + b - c
            pa, pb, pc = abs(q - a), abs(q - b), abs(q - c)
            p = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
        out[i] = (line[i] - p) & 0xFF
    return out


def filtered(rows, bpp, choose):
    """The filtered image data for `rows` (each the unfiltered bytes of one
    scanline). `choose` is a filter type 0-4 for every row, or None for the
    usual heuristic: per row, the filter whose bytes, read as signed, sum
    smallest."""
    out = bytearray()
    prev = bytearray(len(rows[0]))
    for line in rows:
        if choose is None:
            best = None
            for ft in range(5):
                cand = _filter_row(ft, line, prev, bpp)
                cost = sum(v if v < 128 else 256 - v for v in cand)
                if best is None or cost < best[0]:
                    best = (cost, ft, cand)
            ft, data = best[1], best[2]
        else:
            ft, data = choose, _filter_row(choose, line, prev, bpp)
        out.append(ft)
        out.extend(data)
        prev = line
    return bytes(out)


def _deflate(raw, strategy):
    z = zlib.compressobj(9, zlib.DEFLATED, 15, 9, strategy)
    return z.compress(raw) + z.flush()


def encode(w, h, rgb=None, indices=None, palette=None):
    """The smallest 8-bit non-interlaced PNG this module can write for a
    picture, with no ancillary chunks: colour type 3 from `indices` and
    `palette` [(r, g, b), ...], or colour type 2 from `rgb` (R, G, B bytes,
    row-major). Every filter choice is tried under zlib's two useful
    strategies at level 9, and the smallest wins; the choice is deterministic,
    so the same picture always encodes to the same bytes."""
    if indices is not None:
        ctype, bpp, src = 3, 1, indices
    else:
        ctype, bpp, src = 2, 3, rgb
    stride = w * bpp
    rows = [bytearray(src[y * stride:(y + 1) * stride]) for y in range(h)]
    best = None
    for choose in (0, 1, 2, 3, 4, None):
        raw = filtered(rows, bpp, choose)
        for strategy in (zlib.Z_DEFAULT_STRATEGY, zlib.Z_FILTERED):
            body = _deflate(raw, strategy)
            if best is None or len(body) < len(best):
                best = body
    out = SIGNATURE + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, ctype, 0, 0, 0))
    if ctype == 3:
        plte = bytearray()
        for r, g, b in palette:
            plte.extend((r, g, b))
        out += _chunk(b"PLTE", bytes(plte))
    return out + _chunk(b"IDAT", best) + _chunk(b"IEND", b"")


def palettize(rgb, limit=256):
    """(indices, palette) for R, G, B bytes with at most `limit` distinct
    colours, palette in order of first appearance; None when there are more."""
    seen = {}
    palette = []
    indices = bytearray(len(rgb) // 3)
    for i in range(len(indices)):
        c = bytes(rgb[i * 3:i * 3 + 3])
        j = seen.get(c)
        if j is None:
            if len(palette) == limit:
                return None
            j = seen[c] = len(palette)
            palette.append((c[0], c[1], c[2]))
        indices[i] = j
    return bytes(indices), palette
