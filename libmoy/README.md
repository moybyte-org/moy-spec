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
8×8 font, the 64-entry palette, RGB888/RGB565 resolution at flush time, and the
Lua binding with SPEC.md §4.1's sandbox.

**Not here, on purpose:** a VM, a frame loop, a filesystem, a launcher. libmoy
binds to whatever `lua_State` you hand it — `vendor/lua` is a convenience, not a
dependency — and the loop belongs to your platform. The verb table is the narrow
waist, and the Lua binding is the evidence: `src/moy_lua.c` is ~400 lines, which
is what a WASM import table or a native binding would also cost. If binding a
language took a thousand lines the "narrow waist" claim would be false.

`moy_canvas` is a plain struct you place yourself. Nothing here calls `malloc`,
and since the raster is integer-only it does not need libm either.

## Two pixel formats, one raster

SPEC.md §1.1 lets a host keep the canvas as RGB565 rather than palette indices:
*"a host rendering direct to RGB565 pays 150 KB instead — its choice, not the
cart's."* That choice is a compile flag here, not a fork:

```
cc -DMOY_PIXEL_RGB565 ...        /* moy_pixel is uint16_t; 153,600 B */
cc ...                           /* moy_pixel is uint8_t;   76,800 B */
```

On the 565 build you hand the canvas your panel's word for each of the 64
colours once (`moy_canvas_wire`, which is also where a byte-swapped panel is
accommodated), every verb writes those words directly, and the flush is a
`memcpy` instead of a palette pass. Everything else is the same source: the
format-aware code is `src/moy_pixel.h`, about sixty lines, and no verb knows
which build it is in. `make conform-565` runs the whole suite against it — the
replayer resolves back to indices first, so **both builds are judged by the same
golden frames**, which is what makes this a host's choice rather than a second
raster to keep in step.

Which is faster depends on the board, and the difference is smaller than the
argument about it. Indices win where a verb is write-bandwidth-bound (fills)
and cost a palette pass at flush; 565 wins that pass back and suits a display
pipeline — or a 2D accelerator — that cannot consume indices.

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

## Running actual carts

```
make lua            # build/run_cart -- runs a .moy cart through libmoy + Lua
make conform-lua    # the suite again, but through REAL carts rather than traces
make play           # build/moy-play -- a desktop console (SDL2)
```

`moy-play mygame.moy` is a playable console in about 250 lines
(`port/sdl2/main.c`), and that file is the porting layer as a worked example
rather than a description. What a platform owes libmoy is four things:

| | |
|---|---|
| **pixels out** | resolve the index framebuffer through the palette, put it on your glass |
| **buttons in** | map your hardware onto SPEC.md 7.3's seven logical buttons |
| **a clock** | milliseconds |
| **persistence** | 256 signed 32-bit slots, if you have anywhere to put them |

Audio is optional — SPEC.md 8.3 says silence is a valid rendering. Everything
else is libmoy's.

`port/esp-idf/` is the same shim as an IDF component. Its README is explicit
about what has and has not been run on hardware.

`port/wasm/` is the third one, and it is the spec's own web player: libmoy plus
Lua through emscripten, ~296 KB total, built into `runner/` and served by
`moy.py run`. It replaced a MicroPython-WASM build of the reference console that
was three times the size and had to carry a second raster in JavaScript, because
a Python VM cannot fill 76,800 pixels a frame and this can.

## The sandbox is real, not documentation

SPEC.md 4.1's ceiling is enforced by `io`, `os`, `debug`, `package` and
`coroutine` **not being compiled in at all** — their sources are removed from
`vendor/lua`, and the binding opens only `base`, `math`, `string` and `table`
by hand rather than calling `luaL_openlibs` (which would pull all of them in
and leave the sandbox depending on nil-ing them out afterwards). A cart
reaching for any of them fails, as SPEC.md 11 requires of every conforming host.

## Status

**Stages A, B and C: the raster, the Lua binding, and the porting layer.** The
suite passes through both paths — recorded traces and real Lua carts. Next is
hardware verification of the ESP-IDF shim, and audio (SPEC.md 8), which is
absent because silence conforms and nothing yet needed it.

## Licence

MIT. Deliberately: a spec is only portable if its core is. The reference
console built on top of this is a separate thing under its own licence — the
core is meant to be a commodity, and the OS is where a vendor competes.
