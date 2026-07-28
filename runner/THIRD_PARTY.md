# Third-party components in the web player build

The compiled player (micropython.mjs / micropython.wasm) contains:

- **MicroPython** (the `webassembly` port; VM, runtime, stdlib subset) --
  MIT License, Copyright (c) 2013-2026 Damien P. George and contributors.
  https://github.com/micropython/micropython
- **micropython-lib** (frozen stdlib modules) -- MIT License (per-module
  notices in the source), The MicroPython Developers.
  https://github.com/micropython/micropython-lib
- **Lua 5.4** (the cart language VM) -- MIT License,
  Copyright (c) 1994-2024 Lua.org, PUC-Rio. https://www.lua.org/license.html
- **Emscripten runtime support code** (the JS loader glue inside
  micropython.mjs) -- MIT / University of Illinois-NCSA,
  Copyright (c) 2010-2026 Emscripten authors. https://emscripten.org

All are permissive; this file preserves their attribution as those licenses
require when distributing compiled copies.
