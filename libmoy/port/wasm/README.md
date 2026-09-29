# libmoy on the web

The browser as a platform: libmoy plus Lua compiled by emscripten, with a page
supplying a canvas, a keyboard, an AudioContext and localStorage. Same shape as
`port/sdl2` — pixels out, buttons in, a clock, persistence — and the same
console underneath, byte for byte, as an ESP32 links.

```
./build.sh                 # -> ../../../runner (what moy.py web serves)
./build.sh /tmp/out        # somewhere else
EMSDK=~/emsdk ./build.sh   # if emcc is not on PATH
```

| | |
|---|---|
| `main.c` | the host: cart loading, the console wiring, the entry points JS calls |
| `cart.c` | a compiled cart's console: libmoy's wasm binding on the direct-colour raster |
| `page/index.html` | the page |
| `page/player.js` | the platform shim — input, audio, persistence, the rAF loop |
| `page/cart.js` | a compiled cart's module, instantiated beside the console, its imports adapted onto the binding |
| `conform.mjs` | the SPEC.md §11 player protocol, under node |
| `shot.mjs` | screenshot the real page in real headless Chrome |

## What the platform forces

Three things differ from the desktop port, and only three.

**The loop is inverted.** A browser will not let a program block, so there is no
`while (running)`: JS owns `requestAnimationFrame` and calls `moy_web_frame()`.
Every entry point in `main.c` exists because of that.

**The cart arrives as bytes.** There is no filesystem — the page fetches
`carts.json` and hands each file over by its path in the cart's folder
(`moy_web_file`), a file that is not text arriving as base64. The parsers are
otherwise the ones the other ports use.

**Colour resolves in C.** 76,800 palette lookups a frame is the one loop worth
keeping on the wasm side; the page uploads finished RGBA and never learns what a
sprite is.

## Compiled carts

A `"runtime": "wasm"` cart is a module of its own, and the page runs it as a
**sibling** of `moy.wasm` on the browser's engine — never an engine inside the
console. `moy_web_boot` checks the module's shape from its bytes and its
footprint against the player's limit before anything of it exists, and binds a
console to it (`cart.c`: libmoy's wasm binding built with `MOY_WASM_JS`, on the
direct-colour raster under its `moy565_` names). Then `page/cart.js`
instantiates it with one import per row of the binding's table, each an adapter
over that row's C function, generated from the row's signature:

- a scalar passes straight through;
- a `*~` pair — a pointer and the length it covers — is bounds-checked against
  the cart's memory (outside it is a trap), copied into the console's memory,
  passed to C as that copy, and copied back when the call returns, which is how
  `read` and `cfg` write into the cart;
- a pointer the table carries as a plain `i32` (`blit`'s frame and palette,
  `blit565`, `camera`'s and `touch`'s out) is the binding's to reach, and it asks
  the page for it through `moy_wasm_js_span` and `moy_wasm_js_store`, which copy
  in and out the same way.

A trap raised by the binding is thrown back through the cart as an exception,
which unwinds it exactly as a wasm trap does. The page calls the hooks between
`moy_web_wasm_tick` and `moy_web_wasm_present`, and presents only a frame whose
`_draw` finished.

The cart's `par` items run on the page's one thread, one after another: the
cart's memory is not shared, so no worker could reach it, and the frame is the
same as on a host that spreads them over its cores. The binding asks the page
for each through `moy_wasm_js_item`, and `cart.js` sets the cart's exported
`__stack_pointer` to the item's own stack, calls its `_par`, and puts the stack
pointer back.

The cart's `snd` queues its samples in a `moy_stream` in `main.c`, and the
page's audio pull adds them after the synth, so they reach the AudioWorklet
the same way. While the page has no running AudioContext it drains the queue
by the frame's time instead (`moy_web_audio_skip`), so a cart pacing itself on
its stream does not stall waiting for a tap. `window.moy.state.snd` is the
queue's counters: frames queued, frames played, and output frames that found
none.

## Checking it

```
node conform.mjs <cart-dir> <out.bin>          # the player protocol
python3 ../../../conformance/run.py --player "node libmoy/port/wasm/conform.mjs {cart} {out}"
node shot.mjs ../../../examples/brick_siege.moy shot.png --frames 90 --keys ArrowLeft
```

`conform.mjs` runs this exact `moy.wasm` under node and dumps its index
framebuffer, so conformance judges the shipped player rather than a native build
that resembles it. A compiled cart runs through the shipped `cart.js` and is
dumped as its RGB565 frame, which `conformance/wasm_run.py` holds against every
other host. It covers the console completely and the **page** not at all.

`shot.mjs` is the other half, and the one to reach for on any "it looks wrong"
report: canvas sizing, rAF pacing, module loading over HTTP, a listener that
never bound — none of it is visible in a framebuffer dump, and all of it is
visible in a screenshot.

## Notes

- **No `-sFILESYSTEM`.** Emscripten's MEMFS would have let `main.c` keep the
  other ports' `fopen` loaders verbatim, at the cost of ~30 KB of JS glue for a
  filesystem holding five text files. The blob table is smaller and the parsers
  are the same grammar.
- **No worker.** The old MicroPython player needed one to keep a slow VM off the
  main thread. A libmoy frame does not take long enough to be worth the
  postMessage round trip, and a main-thread loop is much easier to debug.
- **Audio is pulled by the frame loop**, not by a callback thread, so unlike the
  SDL2 port nothing locks around a verb — the synth is never re-entered
  mid-call. One AudioWorklet holds the ring and resamples continuously to
  whatever rate the AudioContext actually runs at; starvation decays the last
  sample instead of cutting, which is the difference between a stutter and a pop.
- **...and there is a second, worse audio path, which is not dead code.**
  AudioWorklet requires a **secure context**, so over plain http to anything but
  localhost — a phone on the LAN, a VPN, a colleague's desk — `audioWorklet` is
  simply undefined. Every visitor who is not the person serving the page lands on
  the chunk-scheduler fallback: per-chunk resampling, audible seams the ring does
  not have. Seams beat silence. Deleting it as redundant once made the player
  silent for everyone but the host, which is the kind of bug a harness on
  127.0.0.1 cannot have.
- **A user gesture is required before sound may begin**, so the page opens on a
  start overlay over one already-drawn frame rather than booting straight into
  the cart. A page that starts playing has no legal moment to open an
  AudioContext, and reads as a console with no sound.
- **The cart loading here is a fourth copy** of the `sprites.moygfx` /
  `map.moymap` / manifest parsers (`test/run_cart.c` and `port/sdl2/main.c` have
  the others). Each port being self-contained is deliberate — it is what makes
  one readable as a worked example — but if a fifth appears, the SPEC.md §3
  parsers should move into the library.
