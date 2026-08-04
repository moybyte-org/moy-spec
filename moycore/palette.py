"""The 64-entry palette (SPEC.md 2).

Indices 0-15 are PICO-8's base 16, byte-exact, so a converted cart keeps its
colours. 16-63 extend it with pastels, earth tones, vivid accents, neutrals and
deep shades. The table is DATA (palette.json beside SPEC.md), not code, because
conformance needs exact values -- this module reads it, it does not define it.

A cart may replace the whole table via its manifest (SPEC.md 2.2); `parse`
turns that array into the same (r, g, b) list shape. `pal()` remaps index to
index and is unaffected by which table is loaded -- palette choice and draw-time
remapping are different mechanisms and stay that way.
"""

import json

from . import _data

SIZE = 64

# SPEC.md 2's table: the names it gives indices 0-15. Beyond 15 the spec names
# nothing (they are a gamut, not a vocabulary), so neither does this.
NAMES = {
    "black": 0, "dark_blue": 1, "dark_purple": 2, "dark_green": 3,
    "brown": 4, "dark_grey": 5, "light_grey": 6, "white": 7,
    "red": 8, "orange": 9, "yellow": 10, "green": 11,
    "blue": 12, "indigo": 13, "pink": 14, "peach": 15,
}


def _hex_to_rgb(s):
    s = str(s).strip()
    if s[:1] == "#":
        s = s[1:]
    if len(s) != 6:
        raise _data.DataError("bad palette entry %r (want RRGGBB)" % (s,))
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def parse(entries):
    """A list of 64 "RRGGBB" strings -> a list of 64 (r, g, b) tuples.

    Used for both palette.json and a manifest's own `"palette"` (SPEC.md 2.2) --
    same format, same validation, so a cart-supplied table cannot be looser than
    the default one."""
    if len(entries) != SIZE:
        raise _data.DataError("palette needs %d entries, got %d" % (SIZE, len(entries)))
    return [_hex_to_rgb(e) for e in entries]


def load(name="palette.json"):
    return parse(json.loads(_data.read(name)))


MOY64 = load()


def color(name_or_index):
    """A colour name or number -> a 0-63 index. Unknown names resolve to white,
    which is visible; resolving them to 0 would silently paint black on black."""
    if isinstance(name_or_index, str):
        return NAMES.get(name_or_index, 7)
    return int(name_or_index) & 63


def rgb888_table(pal=None):
    """Flat r,g,b bytes for the whole table -- what a host uploads once and
    indexes per pixel at flush time (SPEC.md 2: "hosts resolve indices to their
    native pixel format at flush time")."""
    pal = MOY64 if pal is None else pal
    out = bytearray(len(pal) * 3)
    for i in range(len(pal)):
        r, g, b = pal[i]
        out[i * 3] = r
        out[i * 3 + 1] = g
        out[i * 3 + 2] = b
    return bytes(out)


def rgb565_table(pal=None):
    """The same table as RGB565 big-endian pairs: 128 bytes, which is the whole
    reason SPEC.md 2.1 caps the index space at 64 -- it fits in fast memory on
    any host."""
    pal = MOY64 if pal is None else pal
    out = bytearray(len(pal) * 2)
    for i in range(len(pal)):
        r, g, b = pal[i]
        v = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        out[i * 2] = (v >> 8) & 0xFF
        out[i * 2 + 1] = v & 0xFF
    return bytes(out)
