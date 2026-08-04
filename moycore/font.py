"""The 8x8 console font (SPEC.md 6).

96 glyphs, ASCII 0x20-0x7F, 8 bytes per glyph, one byte per COLUMN left to
right, LSB = top row. Ships as font.bin beside SPEC.md because the spec is
blunt about why: "the 8x8 font must be byte-identical across implementations or
all text conformance fails". Prose cannot carry glyph data, so it doesn't try.

Codepoints outside the range draw nothing and advance 8px like any glyph -- a
cart printing a degree sign gets a hole, not a crash and not a reflowed line.

font.bin is MicroPython's font_petme128_8x8, MIT-licensed. Shipping the glyphs
means shipping that notice; see THIRD_PARTY.md.
"""

from . import _data

FIRST = 0x20
LAST = 0x7F
WIDTH = 8
HEIGHT = 8
ADVANCE = 8

DATA = _data.read("font.bin", binary=True)

_COUNT = LAST - FIRST + 1
if len(DATA) != _COUNT * WIDTH:
    raise _data.DataError(
        "font.bin is %d bytes, want %d (%d glyphs x %d columns)"
        % (len(DATA), _COUNT * WIDTH, _COUNT, WIDTH))


def glyph(ch):
    """The 8 column-bytes for character `ch`, or None when it is outside
    0x20-0x7F (the caller advances anyway -- see `draw`)."""
    n = ord(ch) - FIRST
    if 0 <= n < _COUNT:
        return DATA[n * WIDTH:(n + 1) * WIDTH]
    return None


def draw(put, s, x, y):
    """Render `s` at (x, y), calling put(px, py) once per set pixel.

    The reference rasterization of `print`: column j left to right, bit 0 of
    each column byte is the TOP row, 8px advance per character including the
    ones that draw nothing. A backend supplies `put`; text ends up identical
    everywhere because the scan order and the bytes are both fixed."""
    cx = int(x)
    y = int(y)
    for ch in str(s):
        col = glyph(ch)
        if col is not None:
            for j in range(WIDTH):
                bits = col[j]
                py = y
                while bits:
                    if bits & 1:
                        put(cx + j, py)
                    bits >>= 1
                    py += 1
        cx += ADVANCE


def width(s):
    """Pixel width of `s` -- len * 8, since the font is fixed-pitch and SPEC.md 6
    gives `print` no scale parameter."""
    return len(str(s)) * ADVANCE
