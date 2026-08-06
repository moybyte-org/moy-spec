# Third-party components in the web player build

The compiled player (`moy.mjs` / `moy.wasm`) contains:

- **Lua 5.4** (the cart language VM, SPEC.md §4) -- MIT License,
  Copyright (c) 1994-2024 Lua.org, PUC-Rio. https://www.lua.org/license.html
- **Emscripten runtime support code** (the JS loader glue in `moy.mjs`, and the
  libc it links) -- MIT / University of Illinois-NCSA,
  Copyright (c) 2010-2026 Emscripten authors. https://emscripten.org
- **MicroPython** -- MIT License, Copyright (c) 2013-2026 Damien P. George and
  contributors. https://github.com/micropython/micropython -- not as code any
  more, but the console font compiled into the raster is MicroPython's
  `framebuf` `font_petme128_8x8`, which SPEC.md §6 makes normative. The notice
  travels with the glyph data; see the repository's own THIRD_PARTY.md.

Everything else -- the raster, the palette, the verb table, the sandbox, the
synth, the page -- is this repository's, under its MIT license.

All are permissive; this file preserves their attribution as those licenses
require when distributing compiled copies.
