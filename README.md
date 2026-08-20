# moy

**A small game console that exists as a spec. The same cart — pixels, buttons,
sound, a little saved state — plays on an ESP32 handheld, a PC or a browser
tab, and the spec is exact enough for those to render it pixel-identically.**

A cart is a folder: a manifest, a Lua script, a sprite sheet, a tilemap, a
sound bank. You hand it to a console and it plays. No install, no build step,
no per-device binary.

- **[SPEC.md](SPEC.md)** — the console: raster, palette, verb table, cart format
- **[GUIDE.md](GUIDE.md)** — writing games: a first cart, then a handbook
- **[PORTING.md](PORTING.md)** — running carts on your own hardware, in the order to build it
- **[RATIONALE.md](RATIONALE.md)** — why each number is what it is

Status: **draft 0.2, unstable.** Names and values will still move.

## Get moy

[**Download the rolling release**](https://github.com/moybyte-org/moy-spec/releases/tag/player-latest):

- **Windows** — `moy-windows-x64.zip`: `moy.exe`, the whole toolchain in one
  executable, plus `moy-play.exe`, the native player — **drag a `.moy` cart
  folder onto it**. Arrows or WASD = d-pad, Z/J = A, X/K = B, Enter or Space =
  run, Esc = quit.
- **Linux / macOS** — `moy-linux-x64.tar.gz` / `moy-macos-arm64.tar.gz`: the
  same pair, `moy` and `moy-play`. The macOS build is Apple Silicon and
  unsigned — first run is right-click → Open.

No Python, no install. From a checkout of this repository, every command below
also runs as `python3 moy.py …` — Python 3.8+ and nothing else.

## Which are you?

### Writing a game → **[GUIDE.md](GUIDE.md)**

```
moy new mygame
moy run mygame.moy
```

Your browser opens with the game running; edit `mygame.moy/main.lua` in your
own editor and save, and it restarts in under a second. Your art tools already
work — the sheet round-trips through indexed PNG and the tilemap through CSV.
`moy export` turns the cart into static files you can host anywhere, itch.io
included, and `moy check` tells you before you ship what the tightest console
would refuse.

[GUIDE.md](GUIDE.md) builds a complete small game from nothing, then covers
each topic in turn — art, audio, saving, budgets, and the dozen things that
catch everyone once.

Coming from PICO-8? `moy demo` fetches Celeste Classic, ports it and plays it
in one command; `moy port cart.p8` does the same for any cart.

### Building a console → **[PORTING.md](PORTING.md)**

Link [`libmoy/`](libmoy/) — the console as dependency-free C99, sandboxed Lua
binding included — or implement the spec yourself in whatever language your
firmware speaks. Either way `conformance/` proves it, and it is reachable on
your first day: every scene ships as a flat verb trace, so a rasterizer can be
checked long before there is a cart loader or a VM.

[PORTING.md](PORTING.md) is the order to build things in, what to refuse
versus ignore versus degrade, how to run the suite against your build, and the
conformance checklist.

## Why this exists

Several people are building small handheld consoles on ESP32-class hardware,
each with its own way of packaging a game — and none of those catalogues can
move. A shared cart format means a game written once plays on all of them,
and a converter written once benefits everybody. The numbers are sized for
that silicon: the whole console fits in about 400 KB of RAM (§1.1), and these
carts run on two real ESP32 boards today.

The spec is deliberately narrow: it describes what a *game* touches, and says
nothing about operating systems, shells or drivers — exactly where consoles
differ and should keep differing.

Past core there is an **extension** mechanism — declare what your cart needs,
and a console that lacks it turns the cart away by name instead of crashing
halfway through a frame. It is currently **empty**, which is the more
interesting fact about it. Every candidate so far turned out to be something a
console could either afford outright or fake convincingly, and both of those
belong in core: `layers`, `view` and `background` all moved there, and the
`~= nil` guard a cart would have written around them was a guard that could
never fire. What is left for an extension is hardware a cart cannot paper over
— a radio, say. SPEC.md 10 has the test.

## The pieces

| | |
|---|---|
| [moycore/](moycore/) | the console as a Python library — stdlib-only: raster, palette, font, cart format, verb table |
| [libmoy/](libmoy/) | the console as a C99 library — no dependencies, no allocation, §4.1-sandboxed Lua binding, and three ports: SDL2 desktop, ESP-IDF component, WebAssembly |
| [runner/](runner/) | the web player: libmoy compiled to WebAssembly, under 350 KB of static files, built by `libmoy/port/wasm` |
| [conformance/](conformance/) | the suite that keeps them honest — one scene per area, each a real cart with a golden frame, and a runner that takes any player. Five builds render every scene pixel-identically, an ESP32-P4 over serial among them — but all five descend from one raster, and its README is candid about what that costs |
| [examples/](examples/) | `brick_siege.moy`, a complete game in core only, written to be read; `verbs.moy`, one screen per verb group |
| [moybyte](https://github.com/moybyte-org/moybyte) | the reference implementation: a PC simulator and two ESP32 handhelds |
| [PURR OS](https://github.com/PastorCatto/PURR-OS-ESP32) | an ESP32 operating system that runs carts from a hand-written console — its own raster, cart loader and Lua binding, no libmoy. The first host outside this repository, and the only one that shares no code with it |
| [proposals/](proposals/) | drafts on top of core: single-file carts (`moy pack`), compiled carts (WASM), sideload, the p8/TIC-80 verb gaps |
| [THIRD_PARTY.md](THIRD_PARTY.md) | attribution that travels with the normative data files |

The known gaps: audio authoring (sprites and maps round-trip through PNG and
CSV; `sfx.moysfx` has only the reference console's on-device editors) and a
TIC-80 converter.

## Contributing

This is early, and the useful contributions are arguments, not patches.

If you do send a patch that touches the documents, `python3 tools/check_docs.py`
is what CI runs on them: it holds the prose to the things that generate its facts
— the suite's own scene count, SPEC.md's section numbers, the player's byte sizes
— because each of those had gone stale in three or four files at once. Its
docstring is also where the rule lives for when a number belongs in prose at all.

If you are building a console, the last section of [PORTING.md](PORTING.md)
names the values most likely to be wrong for hardware this project has not
seen. Saying so in an issue is worth more than a patch: a spec only one device
can implement has failed.

If you have shipped games: everything in §6.1, and anything that made you
think "that would be annoying to write against."

Governance is informal while there is one implementation. Once a second
console passes conformance, this moves somewhere neutral with its
implementers as maintainers. Until then, a breaking change needs agreement
from everyone who has shipped an implementation — the reference console
included.
