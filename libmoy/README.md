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
sandbox, the wasm binding behind a build flag (below), and — as a separate,
optional module — the whole of SPEC.md §8's
synthesizer (`include/moy_audio.h`: eight waveforms, seven effects, the sfx step
sequencer and the music row sequencer with its channel-claiming rules).

**Not here, on purpose:** a VM, a frame loop, a filesystem, a launcher. libmoy
binds to whatever `lua_State` you hand it — `vendor/lua` is a convenience, not a
dependency — and the loop belongs to your platform. The verb table is the narrow
waist, and the two bindings are the evidence: `src/moy_lua.c` and
`src/moy_wasm.c` are each a few hundred lines of glue over the same verbs, which
is what a native binding would also cost. If binding a language took thousands
of lines the "narrow waist" claim would be false.

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
make play           # build/moy-play -- a desktop console (SDL2), compiled carts too
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
console none of it. `moy-play mygame.moy --dump out.bin` is the same console
with no window: the clock stopped, the last finished frame written, which is how
CI runs SPEC.md 11 through it. What a platform owes libmoy is four things:

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
an ESP32 host renders into an I2S DMA buffer and nothing else changes. Its
`moy_stream` is a queue of samples from elsewhere — a compiled cart's `snd` —
added into that buffer after the synth.
Everything else is libmoy's.

`port/esp-idf/` is the same shim as an IDF component. Its README is explicit
about what has and has not been run on hardware.

`port/wasm/` is the third one, and it is the spec's own web player: libmoy plus
Lua through emscripten, under 450 KB of static files, built into `runner/` and
served by `moy.py web`. A compiled cart runs beside it as a sibling module (its
README says how). It replaced a MicroPython-WASM build of the reference console that
was three times the size and had to carry a second raster in JavaScript, because
a Python VM cannot fill 76,800 pixels a frame and this can.

## The sandbox is real, not documentation

SPEC.md 4.1's ceiling is enforced by `io`, `os`, `debug` and `package` **not
being compiled in at all** — their sources are removed from `vendor/lua`, and
the binding opens only `base`, `math`, `string`, `table` and `coroutine` by hand
rather than calling `luaL_openlibs` (which would pull all of them in
and leave the sandbox depending on nil-ing them out afterwards). A cart
reaching for any of them fails, as SPEC.md 11 requires of every conforming host.

## The wasm binding — built only when asked

`src/moy_wasm.c` is the import table of
[`proposals/wasm-runtime.md`](../proposals/wasm-runtime.md) as C: a
`NativeSymbol` array of the verbs, bound to a `moy_console` the way
`moy_lua_open` binds a `lua_State`, with the palette `blit`, `blit565`, `target`
for layers, and `read` routed to a callback the host supplies. It tracks the
proposal, so it is not core, and it costs nobody who does not ask for it: the
file compiles to nothing unless an engine is named. `MOY_WASM` builds it over
WAMR, which registers the array under module `"moy"`; it is then the only file
here that includes WAMR's `wasm_export.h`, from an include path the host
provides, and WAMR is not vendored in libmoy. `MOY_WASM_JS` builds it for a host
whose JavaScript engine runs the cart as a module of its own: the host adapts
each import onto the array's functions and supplies the two that copy to and
from the cart's memory. The verbs, the marshalling and the traps are one body of
C either way, and `moy_wasm_check_bytes` checks a module's shape from its bytes
for an engine that has no loader to ask. The binding needs the direct-colour
build (`MOY_PIXEL_RGB565`), because a palette blit's 256 colours do not fit an
indexed canvas; a program that also runs Lua carts on the index build links the
raster twice, the second copy under the `moy565_` names `port/moy565.h` gives
it. `include/moy_wasm.h` says how a host calls it; how the host loads a module —
interpreter or compiled, from where, with what stack — stays the host's.

Three hosts here run it: the harness below, the desktop player
(`port/sdl2/wasm_cart.c`, WAMR's interpreter) and the web player
(`port/wasm/cart.c` and `page/cart.js`, the cart a sibling module on the
browser's engine). `conformance/wasm_run.py` holds all three to the same RGB565
frames.

```
make wasm-check     # moy check refuses the refusal fixtures and passes hello
make wasm-test      # the binding under WAMR on Linux (fetches WAMR)
make play           # the desktop player, WAMR linked in (fetches WAMR)
```

WAMR is the one thing here fetched from the network, by `wasm-test` and `play`.
The Makefile clones the WAMR fork the reference console pins,
`moybyte-org/wasm-micro-runtime` at the commit in its `WAMR_PIN`, into
`build/wamr/` (gitignored), and builds its interpreter with no WASI and no
builtin libc for the platform it runs on, or the one `WAMR_PLATFORM` names for a
cross build (the release's Windows player is MinGW's). `make wasm-test` then
runs the fixtures in `test/wasm/`. Those are WAT source, never binaries,
assembled by `tools/wat.py` with nothing but Python: a conforming cart whose
frame is held against moycore's own rendering of it, the carts a host must
refuse, and modules that must trap or quit. Needs `git`, `cmake` and a C
compiler. `make play PLAY_WASM=0` builds a player without WAMR, which refuses a
compiled cart as SPEC.md 3.1 says.

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
