# moy

**A small game console that exists as a spec. A cart — pixels, buttons, sound,
a little saved state — plays on a PC, in a browser tab and on ESP32 consoles,
and the spec is exact enough for all of them to draw it pixel for pixel alike.**

A cart is a folder: a manifest, a program, and its assets — a sprite sheet, a
tilemap, a sound bank, and a 128 × 128 cover to show it by. The program is Lua,
which every console runs, or WebAssembly compiled from C or C++ for the carts
that draw more than Lua can. You hand the folder to a console and it plays.

- **[SPEC.md](SPEC.md)** — the console: raster, palette, verbs, cart format, the WebAssembly binding
- **[GUIDE.md](GUIDE.md)** — writing games: a first cart, then a handbook
- **[COMPILED.md](COMPILED.md)** — a compiled cart, from `moy new --wasm` to a board
- **[PORTING.md](PORTING.md)** — running carts on your own hardware, in order
- **[PICO8.md](PICO8.md)** — importing a PICO-8 cart: what converts, what does not
- **[RATIONALE.md](RATIONALE.md)** — why each number is what it is

Status: **draft 0.4, unstable.** Names and values will still move.

## Get moy

[**Download the rolling release**](https://github.com/moybyte-org/moy-spec/releases/tag/player-latest):

- **Windows** — `moy-windows-x64.zip`: `moy.exe`, the whole toolchain in one
  executable, plus `moy-play.exe`, the native player — **drag a `.moy` cart
  folder onto it**. Arrows or WASD = d-pad, Z/J = A, X/K = B, Enter or Space =
  run, Esc = quit.
- **Linux / macOS** — `moy-linux-x64.tar.gz` / `moy-macos-arm64.tar.gz`: the
  same pair, `moy` and `moy-play`. The macOS build is Apple Silicon and
  unsigned — first run is right-click → Open.

No Python, no install. From a checkout of this repository every command below
also runs as `python3 moy.py …`, with Python 3.8+ and nothing else, and `moy`
on its own lists them all.

## Which are you?

### Writing a game → **[GUIDE.md](GUIDE.md)**

```
moy demo                 # fetch Celeste Classic, port it, play it
moy new mygame           # scaffold a Lua cart: manifest, main.lua, editor stubs
moy play mygame.moy      # play it in a window, restarting as you save
```

**Start with `moy demo`:** a real PICO-8 game running as a moy cart seconds
after you ask, with nothing to set up first.

Then your own. `moy play` restarts the game in under a second whenever you
save a file in the cart, and `moy web` is the same loop in the browser player,
for devtools. Your art tools already work: `moy gfx` round-trips the sheet
through indexed PNG and `moy map` the tilemap through CSV. Press **F7** in
`moy play` and the frame on screen becomes the cart's `cover.png`, the picture
a launcher or a store shows it by (§3.6) — or paint one. `moy check` says what
the strictest console would refuse; then `moy export` makes a folder of static
files that plays in any browser (itch.io takes it as it is), `moy pack` makes
the cart one file, and `moy push` copies it onto a connected console.

**When Lua is too slow** for what you want to draw — per-pixel effects, voxel
terrain, textured 3D, an emulator — write the cart in C or C++ and compile it
to WebAssembly, the spec's optional second binding (§16):

```
moy new --wasm plasma    # a C starter; --jet makes a 3D one in C++
moy play plasma.moy      # build it, play it, rebuild it as you save
```

It calls the same verbs and keeps the same assets, and it plays in `moy-play`,
in the browser player and on moybyte's ESP32 consoles; a console without the
binding refuses it by name. A compiled cart can also declare writable files of
its own (§16.12). `moy build` fetches a pinned C compiler the first time it runs,
and [COMPILED.md](COMPILED.md) goes from an empty folder to a cart on a board.

### Building a console → **[PORTING.md](PORTING.md)**

Link [`libmoy/`](libmoy/) — the console as dependency-free C99, sandboxed Lua
binding included — or implement the spec yourself in whatever language your
firmware speaks. Either way `conformance/` proves it, and it is reachable on
your first day: every scene ships as a flat verb trace, so a rasterizer can be
checked long before there is a cart loader or a VM.

The compiled-cart binding is optional. Refusing a `"runtime": "wasm"` cart by
name is conforming, and libmoy carries the binding behind a build flag for a
host that takes it on. A launcher may draw each cart's cover, and
`conformance/covers/` holds the PNG files a cover reader is held to.

[PORTING.md](PORTING.md) is the order to build things in, what to refuse
versus ignore versus degrade, how to run the suite against your build, and the
conformance checklist.

### Importing a PICO-8 cart → **[PICO8.md](PICO8.md)**

`moy port cart.p8` turns a `.p8`, a BBS `.p8.png` or a BBS URL into a Lua
cart: the sheet, the map, the flags, the sfx and music, the label as its cover,
and the cart's own code converted token by token, over a shim that implements
PICO-8's verbs on the moy API. Most carts boot and play.

It is a converter, not an emulator, but there is a PICO-8 machine behind it —
the memory map, the screen palette, the fill pattern, coroutines, the system
font — so the line falls at 16.16 fixed point and at multi-cart games, and the
importer says which side of it a cart is on before it writes. [PICO8.md](PICO8.md)
has what comes across, what does not, and how a corpus of real carts fares.
Read its licensing section first: BBS carts default to CC BY-NC-SA 4.0.

## Carts other people publish

A carts repository publishes built carts as release assets, listed in an
`index.json` with each file's size, sha256 and licence and each cart's cover,
and can keep a copy of every asset beside the index for browsers to read.
moybyte-org's carts are published from one, `moybyte-org/carts`:

```
moy install --index https://moybyte-org.github.io/carts/index.json --list
moy install --index https://moybyte-org.github.io/carts/index.json <id> <carts folder>
```

`moy install` checks every file against the index and asks before it fetches
anything under another licence. `moy index` writes the index for a repository
of your own.

## Why this exists

Several people are building small handheld consoles on ESP32-class hardware,
each with its own way of packaging a game — and none of those catalogues can
move. A shared cart format means a game written once plays on all of them, and
a converter written once benefits everybody. The numbers are sized for that
silicon: the whole console fits in about 400 KB of RAM (§1.1), and these carts
run on ESP32-S3 and ESP32-P4 boards today.

The spec is deliberately narrow: it describes what a *game* touches, and says
nothing about operating systems, shells or drivers — exactly where consoles
differ and should keep differing. Past core, a cart can declare an
**extension** it needs, and a console that lacks it turns the cart away by name
instead of failing halfway through a frame. There are none yet: every
candidate turned out to be something a console could afford outright or fake
convincingly, and those belong in core. What is left for an extension is
hardware a cart cannot paper over — a radio, say. SPEC.md §10 has the test.

## The pieces

| | |
|---|---|
| [moy.py](moy.py) | the CLI, `moy` in the release download; `moy` on its own lists every command |
| [moycore/](moycore/) | the console as a Python library — stdlib-only: raster, palette, font, cart format, covers, verb table |
| [libmoy/](libmoy/) | the console as a C99 library — no dependencies, no allocation, §4.1-sandboxed Lua binding, the §16 binding behind a build flag — and three ports: SDL2 desktop (`moy-play`), ESP-IDF component, WebAssembly |
| [runner/](runner/) | the web player: libmoy compiled to WebAssembly, under 450 KB of static files, built by `libmoy/port/wasm`; a compiled cart runs beside it as a module of its own |
| [conformance/](conformance/) | the suite that keeps them honest — one scene per area, each a real cart with a golden frame; compiled carts held to RGB565 goldens; and the PNG files a cover reader is held to. Every build here renders every scene pixel-identically, but all of them descend from one raster, and its README is candid about what that costs |
| [templates/](templates/) | the compiled-cart starters `moy new --wasm` and `moy new --jet` copy |
| [examples/](examples/) | `brick_siege.moy`, a complete game in core only, written to be read; `verbs.moy`, one screen per verb group |
| [moybyte](https://github.com/moybyte-org/moybyte) | the reference implementation: a console OS on ESP32-S3 and ESP32-P4 boards, in a PC simulator and in the browser |
| [PURR OS](https://github.com/PastorCatto/PURR-OS-ESP32) | an ESP32 operating system that runs carts on a hand-written console — its own raster, cart loader and Lua binding, no libmoy. The first host outside this repository, and the only one that shares no code with it |
| [proposals/](proposals/) | single-file carts (`moy pack`) and sideload (`moy push`), implemented here and required of no host; and the records behind decisions that landed in SPEC.md — the compiled-cart binding with its open items, PICO-8's memory map, the PICO-8 verb gaps |
| [THIRD_PARTY.md](THIRD_PARTY.md) | attribution that travels with the normative data files |

The known gap is audio authoring: the sheet and the map round-trip through PNG
and CSV, but `sounds.json` is written by hand, imported from PICO-8, or made in
the reference console's on-device editors.

## Contributing

This is early, and the useful contributions are arguments, not patches.

If you send a patch at all, `tools/preflight.sh` runs what CI runs, here. It is
not the same as `make -C libmoy test`, and the difference is the point: the
steps `make test` leaves out are the ones that check a COMMITTED ARTIFACT
against the sources it was built from — `runner/`, the browser player — which is
exactly what a change to a header under `libmoy/port/` quietly invalidates.
The wasm half runs in a PINNED emscripten container (`emscripten/emsdk`), because
emcc is not byte-reproducible across versions: rebuilding on whatever this
machine happens to have would produce a different `moy.wasm` and a different
stamp. `--fast` skips that half when you have not touched C.

If you do send a patch that touches the documents, `python3 tools/check_docs.py`
is what CI runs on them: it holds the prose to the things that generate its facts
— the suite's own scene count, SPEC.md's section numbers, the player's byte sizes
— because each of those had gone stale in three or four files at once. Its
docstring is also where the rule lives for when a number belongs in prose at all.

If you are building a console, [PORTING.md](PORTING.md) ends by naming the
three numbers most likely not to fit your board. Telling us in an issue is
worth more than any patch you could send.

If you have shipped games: the §6.1 verbs against a real project, and anything
that made you think "that would be annoying to write against."

Governance is informal while there is one implementation. Once a second
console passes conformance, this moves somewhere neutral with its
implementers as maintainers. Until then, a breaking change needs agreement
from everyone who has shipped an implementation — the reference console
included.
