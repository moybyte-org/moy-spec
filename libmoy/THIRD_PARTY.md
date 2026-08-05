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

## Lua (`vendor/lua/`)

Lua 5.4.7, upstream, MIT-licensed:

    Copyright (C) 1994-2024 Lua.org, PUC-Rio
    https://www.lua.org/  --  full text in vendor/lua/COPYRIGHT

Vendored as a convenience, not a dependency: `moy_lua_open` binds to whichever
`lua_State` you hand it, so a host with its own Lua does not need this copy.

Two things about it are deliberate. It is configured `LUA_32BITS`, which moy
SPEC.md 4.2 requires ("integers are 32-bit and wrap ... floats are 32-bit") and
which SPEC.md 11 assumes of the build that generates golden frames. And the
sources for `io`, `os`, `debug`, `package`, `coroutine` and `linit` are removed
rather than merely left unregistered — SPEC.md 4.1 calls its sandbox "a maximum,
not a suggestion", and this is what makes "absent entirely" true of the machine
code and not only of the global table.
