# Third-party components

This repository is MIT-licensed (see `LICENSE`), but some files in it originate
elsewhere and carry their own attribution. Those are listed here.

## `font.bin` — the console font

`font.bin` is MicroPython's `font_petme128_8x8` (the built-in `framebuf` font),
extracted byte-for-byte: 96 glyphs, ASCII `0x20`–`0x7F`, 8 bytes per glyph, one
byte per column, LSB = top row.

- **MicroPython** — MIT License, Copyright (c) 2013-2026 Damien P. George and
  contributors. https://github.com/micropython/micropython

**Implementers: this attribution travels with the font.** SPEC.md §6 makes these
exact bytes normative — text conformance is a pixel diff, so a conforming
console ships this glyph data. Shipping it means shipping the MIT notice above,
the same as any other copy.

## `palette.json` — indices 0–15

Palette entries 0–15 are PICO-8's base sixteen RGB values, reproduced so that
converted carts keep their exact colors (SPEC.md §2). PICO-8 is by Lexaloffle
Games. A list of color values is not itself a licensable work, so no permission
notice attaches; the origin is recorded here because it is a fact about the
data, not an independent design choice.

## The compiled web player

`runner/moy.wasm` and `runner/moy.mjs` are this repository's own libmoy
compiled to WebAssembly, and they bundle two MIT-licensed projects with it
(Lua 5.4 and Emscripten's runtime support). Their notices are in
[runner/THIRD_PARTY.md](runner/THIRD_PARTY.md).

Because those terms require the notices to travel with every copy,
`runner/LICENSE.txt` is a self-contained version of them and `moy export` copies
it into every web bundle it writes. Exports made before 2026-08-08 shipped the
compiled player without one.

## Ported carts

Carts produced by `moy.py port` / `moy.py demo` are derivative works of their
PICO-8 originals and carry the original's license — **not** this repository's.
PICO-8 BBS carts default to CC BY-NC-SA 4.0. No ported cart is committed to this
repository; `moy.py demo` regenerates one locally on request.
