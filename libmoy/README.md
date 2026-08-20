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
player, and an ESP32-P4 over serial. The suite is the directory above this one,
so there is nothing to point at:

```
make conform
```

It prints a line per scene and a verdict, and exits non-zero if any core scene
differs. Its output is not pasted here: a copy of a program's output in a README
is a screenshot, and this one rotted the next time the suite grew a scene.

That works before there is a Lua VM, a cart loader or a frame loop, because the
suite publishes each scene as a flat verb trace as well as a cart. A rasterizer
can be checked the day it draws its first line — which is the whole reason to
start here.

## What is here, and what is not

**Here:** the indexed raster at any of SPEC.md §3.1's three canvas sizes and
every SPEC.md §6 verb, camera / clip / pal / palt, sprites with flips, scales
and colorkeys, `sspr`, the tilemap, the 8×8 font, the 64-entry palette,
RGB888/RGB565 resolution at flush time, the Lua binding with SPEC.md §4.1's
sandbox, and — as a separate, optional module — the whole of SPEC.md §8's
synthesizer (`include/moy_audio.h`: eight waveforms, seven effects, the sfx step
sequencer and the music row sequencer with its channel-claiming rules).

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
make data
```

regenerates `src/moy_data.c` and records which spec commit it came from. A
transcribed array of 192 numbers would compile, run, look right, and disagree
with every other implementation about colour 37.

(`SPEC` defaults to `..`, the spec directly above. A vendored copy of libmoy in
somebody else's tree overrides it: `make data SPEC=/path/to/moy-spec`.)

## Running actual carts

```
make lua            # build/run_cart -- runs a .moy cart through libmoy + Lua
make conform-lua    # the suite again, but through REAL carts rather than traces
make play           # build/moy-play -- a desktop console (SDL2)
make audio-test     # SPEC.md 8's semantics, asserted numerically
make lowres         # a declared 160x120 canvas really is 19,200 bytes
make test           # all of the above that does not need SDL2
```

`moy-play mygame.moy` is a playable console in under three hundred lines
(`port/sdl2/main.c`, down to the "hot reload" comment), and that file is the
porting layer as a worked example rather than a description. Everything past
that comment is dev-loop convenience: `moy-play --watch mygame.moy` rebuilds
the Lua state whenever the cart's bytes change, which is what `moy play` runs.
It is opt-in, so the default is still a console -- and a platform owes the
console none of it. What a platform owes libmoy is four things:

| | |
|---|---|
| **pixels out** | resolve the index framebuffer through the palette, put it on your glass |
| **buttons in** | map your hardware onto SPEC.md 7.3's seven logical buttons |
| **a clock** | milliseconds |
| **persistence** | 256 signed 32-bit slots, if you have anywhere to put them |

Sound is not among them. SPEC.md 8.3 makes silence a valid rendering, so audio is
a fifth duty you may skip entirely. If you want it, it is libmoy's too — `moy_audio.h`
synthesizes SPEC.md 8 into a buffer and asks the platform for nothing but a
sample rate and somewhere to push samples. The SDL2 port wires it in ~50 lines;
an ESP32 host renders into an I2S DMA buffer and nothing else changes.
Everything else is libmoy's.

`port/esp-idf/` is the same shim as an IDF component. Its README is explicit
about what has and has not been run on hardware.

`port/wasm/` is the third one, and it is the spec's own web player: libmoy plus
Lua through emscripten, under 350 KB of static files, built into `runner/` and
served by `moy.py web`. It replaced a MicroPython-WASM build of the reference console that
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

**Stages A, B and C: the raster, the Lua binding, and the porting layer** — plus
audio, which arrived once a desktop player existed to want it. The suite passes
through both paths — recorded traces and real Lua carts — and the traces pass
against the RGB565 build as well; `make audio-test` asserts SPEC.md 8's semantics
numerically (8.3 exempts audio from pixel conformance, so that is its whole test
story).

**The raster is verified on real silicon**: every conformance scene passes on an
ESP32-P4, where six of the reference console's verbs — and then `print`,
`blit_map` and the sprite path — are calls into this library, drawing to a panel
through its RGB565 build. What is still unverified is the **ESP-IDF shim** in
`port/esp-idf/`: CI builds that component for three target/config combinations
and boots the example under QEMU, so the console runs on an emulated ESP32, but
no pixel has left that directory for a display, and QEMU is not a timing model.

## Licence

MIT. Deliberately: a spec is only portable if its core is. The reference
console built on top of this is a separate thing under its own licence — the
core is meant to be a commodity, and the OS is where a vendor competes.
