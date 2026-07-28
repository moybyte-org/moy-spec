# moy

**A small virtual console, specified so the same cart runs on any of them.**

A moy cart is a folder: a manifest, a Lua script, an indexed sprite sheet, a tilemap,
a sound bank. You hand it to a console and it plays. No install, no build step, no
per-device binary.

- **[SPEC.md](SPEC.md)** — the console: raster, palette, verb table, cart format
- **[RATIONALE.md](RATIONALE.md)** — why each number is what it is

Status: **draft 0.1, unstable.** Names and values will move. §6.1 (batched fills and
the 3D verbs) is explicitly unsettled and is not part of 0.1.

## Write a game

Python 3 and a browser. Nothing else.

```
python3 moy.py new mygame
python3 moy.py run mygame.moy
```

The browser opens with the game running. Edit `mygame.moy/main.lua` in your own
editor and save — the game restarts in under a second. The scaffold includes
`moy-api.lua`, which Lua language servers (VS Code's Lua extension) read for
autocomplete and hover docs on every verb.

```
python3 moy.py export mygame.moy
```

produces a folder of static files that boots straight into your game. Host it
anywhere; zipping the folder and uploading it to itch.io as an HTML5 game works
as-is. The player is the reference console compiled to WebAssembly
([runner/BUILD.md](runner/BUILD.md)); carts run at 60fps with sound in any
modern browser, desktop or phone.

## Why this exists

Several people are building small handheld consoles on similar hardware, each with its
own way of packaging a game. None of those catalogues can move. A shared cart format
means a game written once plays on all of them — and it means a converter written once
(PICO-8, TIC-80) benefits everybody instead of one project.

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
| Reference implementation | [moybyte](https://github.com/nikola-j/moybyte) — two ESP32 boards and a PC simulator |
| PICO-8 converter | exists, converts art, map, sound and code under a compat shim |
| Web player | **works** — [runner/](runner/), the reference console compiled to WASM; `moy.py` wraps it (scaffold, hot-reload run, export) |
| Conformance suite | not started |
| TIC-80 converter | not started |

The web player is what lets anyone try this without owning hardware: a cart opens as
a URL, and `moy.py export` turns any cart into one. It is currently *built from* the
reference implementation, which makes it a faithful mirror of one console rather than
an independent second implementation — the conformance suite is what will let the two
be told apart.

## Contributing

This is early and the useful contributions are arguments, not patches.

If you are building a console: the numbers most likely to be wrong for you are the
**memory floor** (§1.1), the **button set** (§7.3) and the **raster** (§1). Those were
chosen from a small sample of hardware. Say so in an issue if they do not fit yours —
a spec that only one device can implement has failed.

If you have shipped games: everything in §6.1, and anything that made you think "that
would be annoying to write against."

Governance is informal while there is one implementation. Once a second console passes
conformance, this moves somewhere neutral with its implementers as maintainers. Until
then: a breaking change needs agreement from everyone who has shipped an
implementation, and that rule binds the reference console too.
