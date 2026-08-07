# moy

**A small game console that exists as a spec. The same cart — pixels, buttons,
sound, a little saved state — plays on an ESP32 handheld, a PC or a browser
tab, and the spec is exact enough for those to render it pixel-identically.**

A cart is a folder: a manifest, a Lua script, a sprite sheet, a tilemap, a
sound bank. You hand it to a console and it plays. No install, no build step,
no per-device binary.

- **[SPEC.md](SPEC.md)** — the console: raster, palette, verb table, cart format
- **[RATIONALE.md](RATIONALE.md)** — why each number is what it is

Status: **draft 0.1, unstable.** Names and values will still move.

## Get moy

[**Download the rolling release**](https://github.com/moybyte-org/moy-spec/releases/tag/player-latest):

- **Windows** — `moy-windows-x64.zip`: `moy.exe`, the whole toolchain in one
  executable, plus `moy-play.exe`, the native player — **drag a `.moy` cart
  folder onto it**. Arrows or WASD = d-pad, Z/J = A, X/K = B, Enter or Space =
  run, Esc = quit.
- **Linux / macOS** — `moy-linux-x64.tar.gz` / `moy-macos-arm64.tar.gz`: the
  same pair, `moy` and `moy-play`. The macOS build is Apple Silicon and
  unsigned — first run is right-click → Open.

`moy play mygame.moy` runs a cart in the native player (`moy-play`, found
beside `moy`, sound and all); `moy run mygame.moy` is the dev loop — the
browser player, with hot reload.

No Python, no install. From a checkout of this repository, every command below
also runs as `python3 moy.py …` — Python 3.8+ and nothing else.

## Write a game

```
moy new mygame
moy run mygame.moy
```

Your browser opens with the game running. Edit `mygame.moy/main.lua` in your
own editor and save — the game restarts in under a second. The scaffold
includes `moy-api.lua`, which Lua language servers (VS Code's Lua extension)
read for autocomplete and hover docs on every verb.

Your own art tools already work: `moy gfx mygame.moy` round-trips the sprite
sheet through an indexed PNG (Aseprite, GIMP, Piskel), and `moy map` does the
same for the tilemap through CSV (Tiled). Before you ship, `moy check
mygame.moy` tells you what the *strictest* console would say — a sandbox
reach, an undeclared extension, a blown budget — before it surfaces on
somebody else's handheld.

```
moy export mygame.moy
```

turns the cart into a folder of static files that boots straight into your
game. Host it anywhere — zipped and uploaded to itch.io as an HTML5 game, it
works as-is.

[examples/verbs.moy](examples/verbs.moy) walks every verb, one screen per
group: `moy run examples/verbs.moy`.

## Put it on a console

```
moy push mygame.moy
```

finds a connected console and copies the cart over;
[proposals/sideload.md](proposals/sideload.md) is how a console makes itself
findable. An SD card in a reader works today:
`moy push mygame.moy --to /path/to/card`.

## Coming from PICO-8

```
moy demo
```

fetches Celeste Classic, ports it, and runs it in your browser. One command,
nothing to set up first — the quickest way to see what this is.

`moy port cart.p8` does that for any cart: assets near-verbatim (the palette's
first 16 colours are PICO-8's), code mechanically ported to Lua 5.4 under a
compat shim. A port plays 1:1 in a letterbox, since 128 × 128 has no integer
fit in 320 × 240; `--zoom` crops eight edge rows and draws at 2× instead
(`moy demo --zoom` as well). The crop is lossy and per-cart (`--zoom 0,8`
chooses which edge), and ports of BBS carts are personal/dev material — their
default license is CC BY-NC-SA.

## Why this exists

Several people are building small handheld consoles on ESP32-class hardware,
each with its own way of packaging a game — and none of those catalogues can
move. A shared cart format means a game written once plays on all of them,
and a converter written once benefits everybody. The numbers are sized for
that silicon: the whole console fits in about 400 KB of RAM (§1.1), and these
carts run on two real ESP32 boards today.

The spec is deliberately narrow: it describes what a *game* touches, and says
nothing about operating systems, shells or drivers — exactly where consoles
differ and should keep differing. Everything past core is an **extension**: a
cart that needs one declares it, a console that lacks it declines the cart
cleanly, and an extension never redefines what core already covers
(SPEC.md 10).

## The pieces

| | |
|---|---|
| [moycore/](moycore/) | the console as a Python library — stdlib-only: raster, palette, font, cart format, verb table |
| [libmoy/](libmoy/) | the console as a C99 library — no dependencies, no allocation, §4.1-sandboxed Lua binding, and three ports: SDL2 desktop, ESP-IDF component, WebAssembly |
| [runner/](runner/) | the web player: libmoy compiled to WebAssembly, under 350 KB of static files, built by `libmoy/port/wasm` |
| [conformance/](conformance/) | the suite that keeps them honest — one scene per area, each a real cart with a golden frame, and a runner that takes any player. Five builds render every scene pixel-identically, an ESP32-P4 over serial among them — but all five descend from one raster, and its README is candid about what that costs |
| [moybyte](https://github.com/moybyte-org/moybyte) | the reference implementation: a PC simulator and two ESP32 handhelds |
| [proposals/](proposals/) | drafts on top of core: single-file carts (`moy pack`), compiled carts (WASM), sideload |
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

If you are building a console: the numbers most likely to be wrong for you
are the **memory floor** (§1.1), the **button set** (§7.3) and the **raster**
(§1). They were chosen from a small sample of ESP32-class hardware — say so
in an issue if they do not fit yours; a spec only one device can implement
has failed.

If you have shipped games: everything in §6.1, and anything that made you
think "that would be annoying to write against."

Governance is informal while there is one implementation. Once a second
console passes conformance, this moves somewhere neutral with its
implementers as maintainers. Until then, a breaking change needs agreement
from everyone who has shipped an implementation — the reference console
included.
