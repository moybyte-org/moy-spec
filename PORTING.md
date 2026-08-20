# Running moy carts on your hardware

You have a device — a handheld, a firmware, a simulator, an emulator front-end
— and you want the catalogue to run on it. This is the door for you.

SPEC.md is the contract and settles every question of behaviour. This document
is the part it does not contain: what to build first, what you may skip, what
you must refuse, and how to prove you got it right.

The other door is [GUIDE.md](GUIDE.md), for writing carts rather than running
them.

## What a console owes a cart

Less than you think. The console is a fixed-size machine with a small verb
table, and the platform underneath it supplies four things: somewhere to put
pixels, a way to read buttons, a millisecond clock, and somewhere to keep 256
integers. Audio is a fifth and it is optional — §8.2 makes silence a valid
rendering.

Everything else — the raster, the palette, the font, the cart layout, the
sandbox, the tick model — is the spec's, and you can have all of it as a C
library without writing it.

Two routes get you there.

## Route A — link libmoy

[`libmoy/`](libmoy/) is the console as C99: no dependencies, no allocation, the
verb table, the Lua binding with §4.1's sandbox already enforced, and the §8
synthesizer as an optional module. Three ports ship with it — SDL2 desktop,
ESP-IDF component, WebAssembly — and `port/sdl2/main.c` is a complete playable
console in a couple of hundred lines, written to be read as the worked example
of a porting layer.

This is the recommended route, and adopting moy this way should cost you a shim
rather than a project. `libmoy/README.md` is its own documentation.

## Route B — implement it yourself

Entirely legitimate — a spec whose only implementation is somebody else's
library has not proven anything. You are writing the raster in your own
language against your own constraints, and the rest of this document is mostly
for you. Route A implementers should still read **the conformance section**,
**refusal semantics**, and **sideload**, because those are yours either way.

**[PURR OS](https://github.com/PastorCatto/PURR-OS-ESP32) took this route**, and
it is worth reading before you start. It runs moy as an app on ESP32 hardware
with its own raster, its own cart loader and its own Lua binding — none of it
libmoy, and written against the spec as it stood at 0.1. Its platform binding
is around two hundred lines, which is the claim this document keeps making,
made by somebody who did not write the spec: **the console is the part you link
or copy, and the platform is a shim.** It is also the only host this project
knows of that shares no code with this repository, which makes anything it
agrees with worth more than another agreement from inside.

---

## The order to build it in

The point of this order is that **each step is provable before the next one
exists**. Nothing here asks you to have a working console before you can find
out whether your circles are right.

### 1. The raster, from verb traces

Start here, before any Lua, any cart loader, any frame loop.

`conformance/traces/*.json` is every scene as a flat list of verb calls with
integer arguments. A replayer for that format is roughly forty lines in any
language. Write it, point it at a scene, and diff your framebuffer against
`conformance/golden/*.png`.

That gives you a checkable rasterizer on day one. The alternative — build
everything, then find out your `circ` is a pixel wide at r=1 — is how ports go
badly.

The verbs are §6 (primitives, text, camera, clip, pal, palt), §7.1 (sprites)
and §7.2 (the map). The scenes are chosen so that each one fails for a distinct
reason; `conformance/README.md` has the table of what each catches.

Two that catch nearly everyone:

- **`clip` is screen space and applies after `camera`.** An implementation that
  clips in world space passes both features tested separately and fails
  `camera_clip`.
- **`pal` is draw time.** Remapping must not disturb pixels already on the
  canvas (§12.1).

### 2. The palette and the font are data — generate, never transcribe

`palette.json` and `font.bin` sit beside SPEC.md and are normative. Read them
or generate your source from them; do not hand-copy the numbers. A transcribed
array of colours compiles, runs, looks correct, and disagrees with every other
implementation about one entry in the extended range. libmoy's `make data`
exists precisely to make that impossible, and records which spec commit it came
from.

The font is one byte per column, LSB at the top, 96 glyphs covering ASCII. Text
conformance is all-or-nothing: any glyph off by a bit fails every text scene.

### 3. The cart loader, and what to refuse

A cart is a folder (§3). Reading it is the easy half; the rules about *what to
do when something is unexpected* are the half that makes carts portable, and
they are not symmetric:

| the cart says | you should |
|---|---|
| a manifest field you do not know | **ignore it** — vendors annotate carts, and minor versions add fields |
| `"extensions": ["something"]` you lack | **refuse the cart**, by name, before running a frame (§10) |
| `"runtime"` naming a binding you lack | **refuse the cart** (§3.1, §15) — never hand the script to your Lua VM anyway |
| `"canvas"` outside the closed set | **refuse the cart** (§1) — running at a size it did not ask for breaks every coordinate |
| an `"icon"` out of range or past the sheet | **ignore it** and choose your own (§3.4) |
| a map larger than the format allows | **reject it** rather than allocating past your budget (§3.3) |

The line, in §3.4's words, is that capability fields refuse and cosmetic ones
degrade. An icon you cannot draw costs the player nothing; a capability you do
not have costs them a crash halfway through a frame, which is the failure this
format exists to prevent.

Refuse *cleanly* — tell the user which cart, and which requirement. A crash is
not a refusal.

### 4. The Lua sandbox

§4.1 fixes the standard library at exactly `base` (minus a handful of escape
hatches), `math`, `string` and `table`. Absent entirely: `io`, `os`, `debug`,
`package`, `coroutine`.

**This is a ceiling, not a floor.** A host that exposes more does not fail
today; it accumulates carts that run only on it, and that breaks the format for
everyone. The temptation is real, because `luaL_openlibs` is one call and doing
it correctly is a dozen.

The robust implementation is to not compile the libraries in at all, rather
than opening everything and nil-ing entries out afterwards — that is what
libmoy does, and a sandbox by subtraction is one refactor away from being no
sandbox. PURR OS reached the same conclusion independently, from the other side:
it vendors Lua privately for the cart app and leaves `liolib.c`, `loslib.c` and
`loadlib.c` out of the build, so a bug in its sandbox setup has nothing to
reach.

Build Lua with `LUA_32BITS` (§4.2). Nothing stops you shipping a 64-bit build,
and §4.2 says why it still conforms — but its floats diverge from the
reference's in the last digits, so frames captured from it are not golden.

Then write a must-fail test: a cart that reaches for `io` has to fail to load,
on every conforming host. The suite does not check this for you (see below), so
this is a test you own.

### 5. The tick and the buttons

30 Hz, or 60 if the cart asks and you can hold it; if you cannot hold 60 for
that cart, run it at 30 rather than at something unstable in between (§5).

`_update(dt)` then `_draw()`, once per tick. **The one sanctioned degradation**
is skipping `_draw` on alternating ticks while continuing to update at the full
rate: logic stays real-time and motion halves. Do that rather than letting the
tick rate sag, and make sure `dt` always reflects real elapsed time.

Map your hardware onto the logical buttons of §7.3. Four directions plus `a`
and `b` are mandatory; `run` is not. Buttons your device has that the console
does not name are yours to keep — a cart polling for a button you do not
implement must simply read not-pressed.

`btnp` fires once per physical press with no autorepeat. If your input layer
already autorepeats for a menu system, turn it off for the cart.

Two rules about exit that are easy to get backwards: **you own the exit
gesture** — a cart is never required to provide one — and `quit()` is the cart
ending itself, which you honour by returning to wherever it was launched from.
A Lua error also ends the cart, and you must report it with the script line
number rather than swallowing it (§4.3).

### 6. Persistence

256 signed 32-bit slots, per cart (§9). You may defer writes; you must land
them before the cart exits. Keying them by cart identity is yours to design —
the title is not unique, so most hosts hash the cart.

A device with nowhere to write can return 0 for every slot and accept every
write, and carts will behave. That is a real degradation, not a conformance
failure, but say so in your documentation.

### 7. Audio, last and optional

§8 is a synthesizer, not a sample player: eight waveforms generated on the fly,
per-note effects numbered as PICO-8 numbers them, four channels with music
claiming from the top and effects round-robining what is left.

Audio is **excluded from pixel conformance** (§8.3) and two hosts will not
produce bit-identical samples. What matters is the *semantics* — channel
claiming, effect behaviour, the keyed-rest rule that makes imported slides
land, per-row durations — because ported music depends on them musically.

If you want it and you are in C, `libmoy/include/moy_audio.h` renders §8 into a
buffer and asks the platform only for a sample rate and somewhere to push
samples. If you do not want it, implement the verbs as no-ops. They must not
error.

---

## Memory: what to reserve, and where

§1.1 states the floor as a table of allocations and a total, and it is a
**floor, not a target**. Three things about it are worth reading twice:

- **The kind of RAM is unspecified.** Internal SRAM, PSRAM, any mix; §1.1's only
  test is whether your tick survives it. That makes the floor trivial on a board
  with PSRAM and binding only on single-die parts.
- **"However you like" includes shutting things down.** A game mode that
  suspends other subsystems while a cart runs is a perfectly good way to free
  the budget.
- **One full-screen layer is inside the floor.** `make_layer` must therefore
  succeed at least once. Beyond that you may decline and return nil, and carts
  are written to handle it (§6).

Where to put what is a quality question you should measure on your own board,
not a conformance one — a cart can observe none of it. RATIONALE.md's memory
section records what the reference implementation measured on its.

## Two pixel formats, one raster

You may keep the canvas as palette indices, or render directly to RGB565 and
pay roughly double the framebuffer for it. §1.1 makes that the host's choice
explicitly. In libmoy it is a compile flag over the same source, and both
builds are judged by the same golden frames — the suite resolves back to
indices before diffing.

Which is faster depends on your display pipeline, and the difference is smaller
than the argument about it.

Your physical display need not match the canvas: scale and/or letterbox onto
your glass, integer factors recommended. A cart honouring `view(w, h)` is
telling you it only uses a centred region, which is your chance to blow that
region up instead of framing it in black. The cart never learns your
resolution.

## Proving it: the conformance suite

§11 is the definition: an implementation conforms when it runs the suite and
produces pixel-identical output.

```
python3 conformance/run.py --player "./build/yourplayer --headless --dump {out} {cart}"
```

The runner substitutes `{cart}` and `{out}` and invokes your command once per
scene. `conformance/README.md` specifies the two frame formats it will accept
and the exact byte layout of each; the thing to know before you read it is that
one of them is your framebuffer written out verbatim, so a firmware port owes
the suite a single `fwrite` and no image codec whatsoever.

Nothing in a scene moves, and nothing reads a clock, a random number or a
button — so your capture can be any frame you like, and a headless build with a
frame counter is a perfectly good adapter.

There are **two** suites and you need both:

- **The traces** check a raster, and you can reach them on day one.
- **`examples/verbs.moy`** checks a *host* — the tick model, input edges, the
  host-dependent verbs, the provisional ones. It is played and looked at; there
  is no golden for it.

`conformance/run.py --diff out/` writes difference frames for whatever failed,
which is how you find the one row you are wrapping.

The §6.1 verbs (`tri`, `trib`, `sspr`, `tline`) get scenes of their own, printed
with a verdict but left out of the count (§11). They are not part of core 0.2
and nobody is asking you for them — but that is where a real board was caught
disagreeing by thousands of pixels, so run them if you implement them.

### What the suite does not cover

Three gaps, stated plainly so you do not mistake a green run for a full one:

1. **The §4.1 sandbox.** No scene reaches for `io`, so a player passes
   everything here with its sandbox wide open. The suite asks players for
   frames, and a correctly refused cart produces none — so checking the ceiling
   needs a runner that can demand a failure, which has not been designed.
   Write that test yourself; this repository does it for its C core in CI.
2. **Audio**, by design (§8.3).
3. **Anything about your device** — thermals, battery, how it behaves when the
   SD card is pulled. Nobody else can test those.

Also worth knowing about provenance: the goldens are rendered by `moycore`,
libmoy is a transcription of it, and the WebAssembly player agrees with both —
but all three share one lineage. An independent implementation that agrees is
worth more to this project than another one that descends from the same raster.
`conformance/README.md` is candid about what was lost when the last independent
one was retired, and PURR OS is currently the only implementation outside this
repository that could replace it. **If you are writing Route B, your agreement is
evidence nobody here can generate.**

## Extensions: adding your own without forking core

Consoles will do more than core, and that is expected — a shell, a radio, an
authoring format, a second cart language. None of that costs you anything,
provided it arrives as an **extension** (§10) rather than as an edit.

§10 states the single rule, and it is worth reading there rather than
paraphrased here: your additions may not reach into territory core has already
settled, and when the two disagree it is your console that gives way. That is
what lets a cart author treat core as a floor everywhere instead of as your
console's particular dialect.

The mechanism is a manifest declaration, and the register of standard
extensions is **empty** — the README explains why every candidate so far
collapsed back into core. Apply §10's test before you reach for the mechanism:
if a cart can be shielded from the absence of your feature, declaring it buys
the author nothing and costs them every console that lacks it.

A cart may also use your extension *opportunistically* — check the verb exists,
declare nothing — which means your extra capabilities can light up on your
console without making a cart non-portable. That is the pattern to document for
your users.

## Getting carts onto the device

SPEC.md says nothing about how a cart travels, and that stays true. What exists
is a ladder of conventions in `proposals/sideload.md`, with the floor at zero
code:

- **Tier 0 — file drop.** Carts are folders in a directory on storage a user can
  reach, and the root of that storage carries a `moy-console.json` marker naming
  where they live and when you rescan. You implement this by *shipping a text
  file*. That is the whole tier.
- **Tier 1 — serial.** A line-oriented protocol over the USB/UART console you
  already have, around a hundred lines, no network stack. Replies are prefixed
  so they interleave safely with your logging.
- **Tier 2 — network.** mDNS plus a few HTTP endpoints, for consoles that
  already carry a stack. Nobody is asking you to add WiFi for this.

`moy push` probes all three in order and carries no device database — a console
that answers is supported, including one from a vendor this repository has never
heard of. The client side is implemented and tested against mocks; what does not
exist yet is firmware that answers, so **the first console to ship the marker
file is the one that makes the tool real**.

## Showing carts in a launcher

If you draw a shelf, `"icon"` names a small block of tiles from the cart's own
sheet (§3.4). It is a pointer, not an image: no new file, no new codec, no
reserved tiles, and bounded so that a grid of thirty carts cannot cost you
megabytes you never budgeted for. Honour the aspect ratio, scale by integer
factors, and fall back to your own choice when it is absent or out of range.

Cover art — the big authored promotional image — is deliberately not in core
(§12.7). If you want it, that is your shelf's business, not the cart format's.

## The checklist

Before you claim conformance:

- [ ] Every counted scene is pixel-identical, from a `LUA_32BITS` build
- [ ] `examples/verbs.moy` plays and looks right on the real device
- [ ] A cart reaching for `io` fails to load
- [ ] An unknown `extensions` entry refuses the cart by name, before a frame
- [ ] An unknown `runtime` refuses it too, rather than reaching for the Lua VM
- [ ] A `canvas` outside the set refuses; an out-of-range `icon` is ignored
- [ ] Unknown manifest fields are ignored, not fatal
- [ ] 30 Hz holds; a `"fps": 60` cart either holds 60 or runs at 30
- [ ] `dt` is real elapsed time, and dropped frames drop `_draw` only
- [ ] The first `make_layer` succeeds
- [ ] `pmem` survives a power cycle
- [ ] A Lua error ends the cart and reports its line number
- [ ] The player can always exit, without the cart's help
- [ ] Audio is either implemented or a set of no-ops that never error

## If the numbers do not fit your board

Say so, in an issue, with the board.

Three numbers are the likeliest to be wrong on a board nobody here has held:
the **memory floor** (§1.1), the **button set** (§7.3) and the **raster** (§1).
All three were picked from a small sample of ESP32-class devices, and a spec
that only its author's hardware can implement has failed at the one job it had.

That is the most valuable thing a second implementer can contribute, and it is
worth more than a patch.
