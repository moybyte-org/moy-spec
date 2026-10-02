"""The cover: `cover.png` beside the manifest (SPEC.md 3.6).

    read(data)            the profile, strictly: the 128x128 picture as R, G, B
                          bytes, row-major -- or CoverError, naming why a host
                          ignores the file
    problem(data)         None for a cover in the profile, else that reason
    square(w, h, rgb)     any picture -> 128x128: the centre square, reduced
                          by an exact integer step or area-averaged
    encode(rgb)           128x128 R, G, B bytes -> the smallest PNG in the
                          profile (indexed when it has 256 colours or fewer)
    rewrite(data)         `moy build`'s pass: any PNG -> one in the profile
    from_frame(w, h, rgb) F7's: a frame -> (cover bytes, what was done)

The profile is what a host must read; `read` is its reference, and
conformance/covers/ holds the vectors it is tested against. A host that finds a
cover outside it draws as if there were none and never refuses the cart.
"""

import struct

from . import png

NAME = "cover.png"
SIZE = 128
MAX_BYTES = 65536


class CoverError(Exception):
    pass


def read(data):
    """The cover's pixels: SIZE * SIZE * 3 bytes of R, G, B, row-major."""
    if len(data) > MAX_BYTES:
        raise CoverError("it is %d bytes, and a cover is at most %d" % (len(data), MAX_BYTES))
    try:
        parts = png.chunks(data)
    except png.PngError as exc:
        raise CoverError(str(exc))
    if parts[0][0] != b"IHDR" or len(parts[0][1]) != 13:
        raise CoverError("the first chunk is not a 13-byte IHDR")
    w, h, depth, ctype, comp, filt, interlace = struct.unpack(">IIBBBBB", parts[0][1])
    if (w, h) != (SIZE, SIZE):
        raise CoverError("it is %dx%d, and a cover is %dx%d" % (w, h, SIZE, SIZE))
    if depth != 8:
        raise CoverError("its bit depth is %d, and a cover's is 8" % depth)
    if ctype not in (2, 3):
        raise CoverError("its colour type is %d, and a cover's is 3 (indexed) or 2 (RGB)"
                         % ctype)
    if comp or filt:
        raise CoverError("unknown compression or filter method")
    if interlace:
        raise CoverError("it is interlaced")
    plte = None
    idat = bytearray()
    for tag, body in parts[1:]:
        if tag == b"IDAT":
            idat.extend(body)
        elif tag == b"PLTE":
            if ctype == 3:
                if idat:
                    raise CoverError("PLTE comes after the image data")
                if len(body) % 3 or not 3 <= len(body) <= 768:
                    raise CoverError("PLTE holds %d bytes, not 1-256 entries" % len(body))
                plte = body
        elif tag == b"tRNS":
            raise CoverError("it has a tRNS chunk, and a cover has no transparency")
        elif tag != b"IEND" and not (tag[0] & 0x20):
            raise CoverError("it has a critical chunk %s that is not a cover's"
                             % tag.decode("latin-1"))
    if ctype == 3 and plte is None:
        raise CoverError("it is indexed and has no PLTE before its image data")
    bpp = 3 if ctype == 2 else 1
    try:
        raw = png._inflate(bytes(idat), SIZE * (1 + SIZE * bpp))
        px = png._unfilter(raw, SIZE, SIZE, bpp)
    except png.PngError as exc:
        raise CoverError(str(exc))
    if ctype == 2:
        return bytes(px)
    entries = len(plte) // 3
    out = bytearray(SIZE * SIZE * 3)
    for i in range(SIZE * SIZE):
        v = px[i]
        if v >= entries:
            raise CoverError("a pixel names palette entry %d of %d" % (v, entries))
        out[i * 3:i * 3 + 3] = plte[v * 3:v * 3 + 3]
    return bytes(out)


def problem(data):
    try:
        read(data)
    except CoverError as exc:
        return str(exc)
    return None


def _spans(side):
    """For each of the SIZE output pixels along an axis, [(source offset,
    weight), ...] over a `side`-pixel span. Weights are overlaps in units of
    1/(SIZE * side) of the span, so each output's weights sum to `side`."""
    out = []
    for o in range(SIZE):
        start, end = o * side, (o + 1) * side
        cells = []
        i = start // SIZE
        while i * SIZE < end:
            cells.append((i, min(end, (i + 1) * SIZE) - max(start, i * SIZE)))
            i += 1
        out.append(cells)
    return out


def square(w, h, rgb):
    """(SIZE x SIZE R, G, B bytes, what was done) for a w x h picture: its
    centre square (the largest one, at ((w - side) // 2, (h - side) // 2)),
    then reduced to SIZE x SIZE -- by taking every k-th pixel when the side
    is k * SIZE, else by area-averaging: each output pixel is the mean of the
    source area it covers, weighted by overlap, rounded half up, in integer
    arithmetic. `what` is None when the picture was already SIZE x SIZE."""
    side = min(w, h)
    x0, y0 = (w - side) // 2, (h - side) // 2
    if (w, h) == (SIZE, SIZE):
        return bytes(rgb), None
    how = [] if w == h else ["the centre %dx%d" % (side, side)]
    out = bytearray(SIZE * SIZE * 3)
    if side % SIZE == 0:
        k = side // SIZE
        for oy in range(SIZE):
            row = ((y0 + oy * k) * w + x0) * 3
            for ox in range(SIZE):
                s = row + ox * k * 3
                out[(oy * SIZE + ox) * 3:(oy * SIZE + ox) * 3 + 3] = rgb[s:s + 3]
        if k > 1:
            how.append("every %s pixel" % _nth(k))
    else:
        spans = _spans(side)
        cols = [0] * (side * SIZE * 3)              # rows of the square, columns reduced
        for y in range(side):
            src = ((y0 + y) * w + x0) * 3
            for ox in range(SIZE):
                r = g = b = 0
                for i, wt in spans[ox]:
                    s = src + i * 3
                    r += rgb[s] * wt
                    g += rgb[s + 1] * wt
                    b += rgb[s + 2] * wt
                d = (y * SIZE + ox) * 3
                cols[d], cols[d + 1], cols[d + 2] = r, g, b
        total = side * side
        half = total // 2
        for oy in range(SIZE):
            for ox in range(SIZE):
                r = g = b = 0
                for i, wt in spans[oy]:
                    s = (i * SIZE + ox) * 3
                    r += cols[s] * wt
                    g += cols[s + 1] * wt
                    b += cols[s + 2] * wt
                d = (oy * SIZE + ox) * 3
                out[d] = (r + half) // total
                out[d + 1] = (g + half) // total
                out[d + 2] = (b + half) // total
        how.append("area-averaged to %dx%d" % (SIZE, SIZE))
    return bytes(out), "%dx%d -> %dx%d: %s" % (w, h, SIZE, SIZE, ", ".join(how))


def _nth(k):
    return "%d%s" % (k, {1: "st", 2: "nd", 3: "rd"}.get(k if k < 20 else k % 10, "th"))


def encode(rgb):
    """SIZE x SIZE R, G, B bytes -> the smallest PNG in the profile."""
    pal = png.palettize(rgb)
    if pal is not None:
        return png.encode(SIZE, SIZE, indices=pal[0], palette=pal[1])
    return png.encode(SIZE, SIZE, rgb=rgb)


def from_frame(w, h, rgb):
    """(cover bytes, what was done or None) for a frame as R, G, B bytes."""
    pixels, how = square(w, h, rgb)
    return encode(pixels), how


def rewrite(data):
    """(bytes in the profile, [what changed]) for any PNG. The file comes back
    unchanged when it is already in the profile, carries only the critical
    chunks, and is no larger than this module's own encoding of it. Raises
    CoverError when the file is not a PNG this module can decode."""
    try:
        d = png.decode(data)
    except png.PngError as exc:
        raise CoverError("not a PNG this tool can read: %s" % exc)
    why = problem(data)
    notes = []
    if (d.w, d.h) == (SIZE, SIZE) and d.indices is not None:
        out = png.encode(SIZE, SIZE, indices=d.indices, palette=d.palette)
    else:
        pixels, how = square(d.w, d.h, d.rgb)
        if how:
            notes.append(how)
        out = encode(pixels)
    if why is not None and not notes:
        notes.append("out of the profile: %s" % why)
    if d.has_alpha:
        notes.append("its transparency flattened onto black")
    if why is None and not d.ancillary and len(data) <= len(out):
        return data, notes
    if d.ancillary:
        notes.append("dropped %s" % ", ".join(t.decode("latin-1") for t in d.ancillary))
    return out, notes
