# The web player build

These four files are the moy web player: **libmoy compiled to WebAssembly** --
the same C console an ESP32 links -- plus Lua 5.4, plus a page that supplies a
canvas, a keyboard and an AudioContext and nothing else. Fully static; a cart
bundle beside them is a playable game at a URL.

| | |
|---|---|
| `moy.wasm` | the console: raster, font, palette, synth, verb table, sandbox, Lua |
| `moy.mjs` | emscripten's loader glue |
| `index.html` | the page |
| `player.js` | the platform shim -- canvas, input, audio, localStorage |

`LICENSE.txt` is the fifth file and the only one that is not the player: it ships
*with* an export, because moy.wasm has Lua and Emscripten's runtime compiled in
and MIT requires their notices to accompany every copy. It is not part of the
build, not in the stamp, and `build.sh` leaves it alone.

The source is [`libmoy/port/wasm/`](../libmoy/port/wasm/), a sibling of the SDL2
and ESP-IDF ports. Rebuilding needs emscripten and nothing else:

    python3 moy.py player            # which build this is; do the files still match
    python3 moy.py player --build    # rebuild from libmoy (needs emcc)

`runner/VERSION` stamps the build -- commit, branch, toolchain and a sha256 per
file -- so "which player is this?" has an answer in the tree, and a rebuild is
an ordinary reviewable diff. A hash mismatch means the bundle was edited by
hand rather than the source it came from, which is worth catching: that edit
survives exactly until the next rebuild silently reverts it.

It is checked in, deliberately. The README promises Python and a browser and
nothing else, and a `moy.py run` that needed a 1 GB toolchain on first use
would not be that.

## Why it is not the reference console

It used to be: a MicroPython-WASM build of
[moybyte](https://github.com/moybyte-org/moybyte)'s console, de-branded by
stubbing out 24 shell modules, pinned here by hash. That worked, but it made
the spec's own player a downstream artifact of one implementation -- and it
shipped an 825 KB Python interpreter to run carts the spec writes in Lua. The
page also had to carry a complete second raster in JavaScript, because
MicroPython cannot fill 76,800 pixels a frame, so the wasm emitted draw
commands and JS replayed them.

libmoy rasterizes in C at WebAssembly speed, so the page just uploads finished
RGBA and the replayer is gone. **1,001,728 bytes down to under a third of that**,
and one raster instead of three. Most of what is left is the wasm; the loader
glue, the page and the shim have grown since the swap, as the page learned what
real phones do. The exact byte count per file is in `VERSION`, which is written
by the build — so it is a number nobody has to maintain, and this paragraph does
not restate it.

## It is conformance-checked, like every other implementation

    node libmoy/port/wasm/conform.mjs {cart} {out}

speaks the SPEC.md §11 player protocol and dumps the index framebuffer straight
out of this same `moy.wasm`, so `conformance/run.py --player` judges the shipped
player rather than something resembling it. CI runs it on every push.

`node libmoy/port/wasm/shot.mjs <cart.moy>` is the other half: it serves these
files to real headless Chrome and screenshots the canvas. Reach for that on any
"it looks wrong" report -- a framebuffer dump cannot see canvas sizing, rAF
pacing, or a listener that never bound.

## Licensing of these artifacts

This build is entirely this repository's own source plus permissively-licensed
components, all under the MIT license -- so the player can be embedded and
redistributed without friction. Third-party components inside the build are
listed in THIRD_PARTY.md (their notices ride along as those licenses require).
