# Third-party notices

## The 8x8 font (`src/moy_data.c`, `moy_font_data`)

The glyph data is MicroPython's `font_petme128_8x8`, generated into this
repository from the moy spec's normative `font.bin` by `tools/embed_data.py`.
It is not this project's work:

    MicroPython (extmod/font_petme128_8x8.h) -- The MIT License (MIT)
    Copyright (c) 2013, 2014 Damien P. George
    https://github.com/micropython/micropython

SPEC.md 6 requires the font to be byte-identical across implementations, so
these bytes travel with every conforming console -- and this notice travels
with them.

## The palette (`src/moy_data.c`, `moy_palette_default`)

Generated from the spec's normative `palette.json`. Indices 0-15 are PICO-8's
base palette, reproduced byte-exact by SPEC.md 2 so converted carts keep their
colours; PICO-8 is Lexaloffle Games LLP's, and the values are stated as data in
a public specification rather than copied from its source.
