# libmoy

**The [moy](https://github.com/moybyte-org/moy-spec) console as a C library.**
No dependencies, no allocation, C99. You supply pixels out and buttons in; the
console is the part you link.

```c
#include "moy.h"

static uint8_t framebuffer[MOY_W * MOY_H];   /* yours: static, PSRAM, wherever */
moy_canvas c;

moy_canvas_init(&c, framebuffer, MOY_W, MOY_H);
moy_cls(&c, 1);
moy_circ(&c, 160, 120, 20, 8);
moy_print(&c, (const uint8_t *)"HELLO", 5, 8, 8, 7);

moy_palette_rgb565(&c, NULL, your_panel_buffer);   /* the only colour-aware step */
```

## Why

moy's premise is that several vendors' handhelds run the same cart. The
reference implementation is MicroPython — so "implement moy" has meant "adopt
MicroPython", which is a large ask of an ESP-IDF or Arduino firmware author and
not something the spec actually requires.

The spec requires a raster, a palette, a font, a cart layout and a verb table.
That is what this is. **Adopting moy should cost you a porting shim, not a
project.**

## Verified against the spec, not against itself

libmoy has no test suite of its own devising. It runs
[moy-spec's conformance suite](https://github.com/moybyte-org/moy-spec/tree/main/conformance)
— the same golden frames that check the reference console, the WebAssembly
player, and an ESP32-P4 over serial:

```
make conform SPEC=../moy-spec
```

```
  ok    primitives      ok    camera_clip
  ok    edges           ok    pal_palt
  ok    text            ok    sprites
  ok    text_bytes      ok    tilemap
                        ok    provisional  (excluded, not counted)

all 8 core scenes pixel-identical.
```

That works before there is a Lua VM, a cart loader or a frame loop, because the
suite publishes each scene as a flat verb trace as well as a cart. A rasterizer
can be checked the day it draws its first line — which is the whole reason to
start here.

## What is here, and what is not

**Here:** the 320×240 indexed raster and every SPEC.md §6 verb, camera / clip /
pal / palt, sprites with flips, scales and colorkeys, `sspr`, the tilemap, the
8×8 font, the 64-entry palette, and RGB888/RGB565 resolution at flush time.

**Not here, on purpose:** a Lua VM, a frame loop, a filesystem, a clock, a
launcher. SPEC.md §4 says a cart is Lua 5.4 and §0 puts operating systems
permanently out of scope; which Lua, and which loop, are yours. The verb table
is the narrow waist — a Lua binding, a WASM import table and a native binding
are each a few hundred lines of glue on top of this, rather than a new port of
the console.

`moy_canvas` is a plain struct you place yourself. Nothing here calls `malloc`.

## The palette and the font are generated

SPEC.md §2 makes the colour table data rather than prose "because conformance
needs exact values", and §6 says the font "must be byte-identical across
implementations or all text conformance fails". So neither is hand-written:

```
make data SPEC=../moy-spec
```

regenerates `src/moy_data.c` and records which spec commit it came from. A
transcribed array of 192 numbers would compile, run, look right, and disagree
with every other implementation about colour 37.

## Status

**Stage A: the raster, conforming.** Next is the Lua binding (the VM is already
vendored C in the reference implementation), then the porting layer with SDL2
and ESP-IDF as worked examples.

## Licence

MIT. Deliberately: a spec is only portable if its core is. The reference
console built on top of this is a separate thing under its own licence — the
core is meant to be a commodity, and the OS is where a vendor competes.
