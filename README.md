# moy

**A small game console that exists as a spec. The same cart — pixels, buttons,
sound, a little saved state — plays on an ESP32 handheld, a PC simulator or a
browser tab, and the spec is exact enough for those to render it pixel-identically.**

A moy cart is a folder: a manifest, a Lua script, an indexed sprite sheet, a tilemap,
a sound bank. You hand it to a console and it plays. No install, no build step, no
per-device binary.

- **[SPEC.md](SPEC.md)** — the console: raster, palette, verb table, cart format
- **[RATIONALE.md](RATIONALE.md)** — why each number is what it is
- **[THIRD_PARTY.md](THIRD_PARTY.md)** — attribution that travels with the
  normative data files (the console font is MicroPython's, MIT)

Status: **draft 0.1, unstable.** Names and values will move. §6.1 (batched fills and
the 3D verbs) is explicitly unsettled and is not part of 0.1.

## Write a game

Python 3.8+ and a browser. Nothing else — no packages, no build step. Any OS
(on Windows, `python` instead of `python3`; the player runs in the browser, so
the OS never touches the game).

```
python3 moy.py new mygame
python3 moy.py run mygame.moy
```

The browser opens with the game running. Edit `mygame.moy/main.lua` in your own
editor and save — the game restarts in under a second. The scaffold includes
`moy-api.lua`, which Lua language servers (VS Code's Lua extension) read for
autocomplete and hover docs on every verb.

Before you ship, `python3 moy.py check mygame.moy` tells you what the *tightest*
conforming host would say — a reach past the §4.1 sandbox, an extension you use but
never declared, a map past the §1.1 budget, a cart that can't be played with buttons
alone. Those are the failures that otherwise surface on somebody else's handheld,
which is the worst possible place for them.

Your own art tools work on the assets: `moy.py gfx mygame.moy` round-trips
`sprites.moygfx` through an indexed PNG (Aseprite, GIMP, Piskel), and `moy.py map`
does the same for `map.moymap` through CSV, which is what Tiled reads and writes.

```
python3 moy.py export mygame.moy
```

produces a folder of static files that boots straight into your game. Host it
anywhere; zipping the folder and uploading it to itch.io as an HTML5 game works
as-is. The player is the reference console compiled to WebAssembly
([runner/BUILD.md](runner/BUILD.md)); carts run at 60fps with sound in any
modern browser, desktop or phone.

[examples/verbs.moy](examples/verbs.moy) walks every core verb, one screen per
group — living documentation, a smoke test for any new implementation, and the
seed of the conformance suite. Screens that go beyond core say so on-screen:
the standard extensions (`layers`, declared in its manifest) and the §6.1
provisional verbs are labeled, so what a minimal host must pass stays obvious.
`python3 moy.py run examples/verbs.moy`.

Coming from PICO-8: `moy.py port cart.p8` converts a cart — assets near-verbatim
(the palette's first 16 colours are PICO-8's, the sheet format is `__gfx__`),
code mechanically ported to Lua 5.4 under a p8 compat shim. And

```
python3 moy.py demo
```

fetches Celeste Classic, ports it, and runs it in your browser. (PICO-8 BBS
carts default to CC BY-NC-SA 4.0 — ports are personal/dev material with
attribution, not something to republish.)

A port runs 1:1 by default, because 128 × 128 has no integer scale that fits
320 × 240 — 2× is 256 × 256, sixteen pixels too tall — so it sits in a
letterbox. **`--zoom`** trades those rows for size: it crops four off the top
and four off the bottom, and the port then *draws* at 2×, filling the height at
256 × 240.

```
python3 moy.py port cart.p8 --zoom        # or: moy.py demo --zoom
python3 moy.py port cart.p8 --zoom 0,8    # take all eight off the bottom
```

The scaling is done by the cart, inside its compat shim — it is not asked of
the host — so a zoomed port looks the same on a handheld, a simulator and a
browser tab, needing no extension and no hardware scaler. It costs four times
the fill rate.

Two things to know first. The crop is **lossy and per-cart**: a game drawing
HUD at the very top or bottom loses it, which is what `T,B` is for — Celeste's
summit timer sits at y=4, so it survives four rows off the top but not eight.
And text does not scale, since §6 fixes `print` at 8px, so a zoomed port
positions its text at scale while the glyphs stay 8 pixels.

## Why this exists

Several people are building small handheld consoles on ESP32-class hardware, each
with its own way of packaging a game. None of those catalogues can move. A shared
cart format means a game written once plays on all of them — and it means a
converter written once (PICO-8, TIC-80) benefits everybody instead of one project.

The numbers are sized for that silicon, and run on it today: the whole console
fits in about 400 KB of RAM (§1.1), and the reference implementation plays these
carts on two real ESP32 boards, not just in a simulator.

The spec is deliberately narrow. It describes what a *game* touches: pixels, buttons,
sound, a little saved state. It says nothing about operating systems, windows, drivers
or app lifecycle, because those are exactly where these projects differ and should
keep differing.

## core, and what sits above it

**moy core** is the part every implementation provides, and therefore the part a cart
can rely on anywhere. It is small on purpose.

Consoles will do more than core, and should. A radio, a windowing shell, a second cart
language, an authoring format — none of that is core, and none of it is discouraged.
It is an **extension**: a cart that needs one says so, and a console that lacks it
declines the cart cleanly. Standard extensions are specified so two consoles
implementing the same one agree; anything vendor-specific is namespaced
(`vendor.feature`) and cannot collide with a future standard.

The line between the two: a capability a cart can *degrade around* belongs in core
(local multiplayer asks how many pads there are and adapts). A capability whose
absence a cart cannot paper over is an extension. A capability whose behaviour cannot
be promised across transports — networking — is neither, and lives in vendor space
until there is something real to generalise from.

The rule that keeps this from fragmenting: **an extension must never redefine
something core already covers.** Where an implementation and core disagree on core's
own ground, the implementation is what changes — including the reference one.

## Status of the pieces

| | state |
|---|---|
| Spec text | draft, readable, §6.1 open |
| Reference implementation | [moybyte](https://github.com/moybyte-org/moybyte) — a PC simulator plus two ESP32 devices: an ESP32-S3 handheld at the native 320 × 240, and an ESP32-P4 board driving it windowed on a 1024 × 600 desktop |
| Console as a library, Python | **works** — [moycore/](moycore/), MIT, stdlib-only: the raster, palette, font, sheet, map, cart format and verb table. Byte-identical to the reference console's rasterizer |
| Console as a library, **C** | **works** — [libmoy/](libmoy/), MIT, C99, no dependencies and no allocation. Under 6 KB of code, and it passes the conformance suite. Implementing moy is a porting shim, not a project |
| PICO-8 converter | exists, converts art, map, sound and code under a compat shim |
| Web player | **works** — [runner/](runner/), the reference console compiled to WASM; `moy.py` wraps it (scaffold, hot-reload run, export) |
| Conformance suite | **runs** — [conformance/](conformance/), 9 scenes as real carts + golden frames + a runner that takes any player. Four implementations agree on every scene: moycore, the reference console's rasterizer, the web player's JS replayer, and an **ESP32-P4** over serial |
| Cart checker | **works** — `moy.py check`: manifest, sandbox ceiling, undeclared extensions, the §1.1 budget |
| Single-file cart | proposed — [proposals/single-file-cart.md](proposals/single-file-cart.md), implemented as `moy.py pack` |
| TIC-80 converter | not started |

The web player is what lets anyone try this without owning hardware: a cart opens as
a URL, and `moy.py export` turns any cart into one. It is *built from* the reference
implementation, which makes it a faithful mirror of one console rather than an
independent second implementation — telling the two apart is what the conformance
suite is for, and it now exists.

Five implementations now agree on every scene, and the ones that matter most are
those sharing no code with each other. moycore was extracted from the
reference console's rasterizer, so [parity.py](conformance/parity.py) proves the
extraction faithful and could never catch a bug that was always in it. The web
player's JavaScript replayer shares no code with either, and
[player.mjs](conformance/player.mjs) runs the suite through it headlessly, in plain
node, with no browser and no dependencies. Its first run found the console drawing
its FPS chip into the cart's own framebuffer.

Another is the hardware. The suite runs on an ESP32-P4 over serial, which is where
the C rasterizer and §1.1's memory floor actually are; its first run reproduced two
bugs the web player had already found, confirming they were never web-specific.

And [libmoy/](libmoy/) is the C core a vendor would actually link — checked by the
same goldens, from the same repository, on every push. That is the point of it
being in-tree rather than off in its own project: a change to the spec turns the C
implementation red immediately, with no version to bump.

## Contributing

This is early and the useful contributions are arguments, not patches.

If you are building a console: the numbers most likely to be wrong for you are the
**memory floor** (§1.1), the **button set** (§7.3) and the **raster** (§1). Those were
chosen from a small sample of ESP32-class hardware. Say so in an issue if they do not
fit yours — a spec that only one device can implement has failed.

If you have shipped games: everything in §6.1, and anything that made you think "that
would be annoying to write against."

Governance is informal while there is one implementation. Once a second console passes
conformance, this moves somewhere neutral with its implementers as maintainers. Until
then: a breaking change needs agreement from everyone who has shipped an
implementation, and that rule binds the reference console too.
