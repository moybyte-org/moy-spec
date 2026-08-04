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


def glyph(code):
    """The 8 column-bytes for byte value `code`, or None outside 0x20-0x7F (the
    caller advances anyway -- see `draw`)."""
    n = code - FIRST
    if 0 <= n < _COUNT:
        return DATA[n * WIDTH:(n + 1) * WIDTH]
    return None


def as_bytes(s):
    """A string argument to `print` as the BYTE sequence SPEC.md 6 says it is.

    `bytes`/`bytearray` pass through. A `str` is taken one byte per character,
    NOT UTF-8-encoded -- because in the only language core defines, a string IS
    a byte string, and a host handing moycore a str is representing those bytes.
    UTF-8-encoding here would make `print(chr(0xFF))` advance 16px in Python and
    8px in Lua for the same cart, which is exactly the disagreement that made
    this rule necessary.

    A character above U+00FF cannot be one byte, so it is a programming error
    rather than something to guess at."""
    if isinstance(s, (bytes, bytearray)):
        return s
    s = str(s)
    out = bytearray(len(s))
    for i in range(len(s)):
        c = ord(s[i])
        if c > 0xFF:
            raise ValueError(
                "print() takes a byte string; U+%04X does not fit in one byte "
                "(encode it yourself if you meant UTF-8)" % c)
        out[i] = c
    return out


def draw(put, s, x, y):
    """Render `s` at (x, y), calling put(px, py) once per set pixel.

    The reference rasterization of `print`: one BYTE per cell, column j left to
    right, bit 0 of each column byte is the TOP row, 8px advance per byte
    including the ones that draw nothing.

    Bytes, not codepoints (SPEC.md 6). A Lua string is a byte string, the
    device's C text kernel walks bytes, and MicroPython's framebuf.text -- which
    this font came from and matches -- walks bytes. An implementation that
    decoded first would advance the cursor 8px for a two-byte character where
    every other host advances 16, so the same cart would lay out differently on
    a desktop simulator and a handheld."""
    cx = int(x)
    y = int(y)
    for code in as_bytes(s):
        col = glyph(code)
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
    """Pixel width of `s` -- one 8px cell per BYTE, since the font is
    fixed-pitch and SPEC.md 6 gives `print` no scale parameter."""
    return len(as_bytes(s)) * ADVANCE
