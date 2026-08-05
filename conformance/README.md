# The conformance suite

> SPEC.md 11: *An implementation conforms when it runs the conformance suite and
> produces pixel-identical output.*

This is that suite. Nine scenes, eight of them counted; each is a real moy cart
plus a golden frame.

```
python3 conformance/run.py                    # self-test (moycore)
python3 conformance/run.py --player "CMD"     # test your player
python3 conformance/run.py --diff out/        # write diff frames for failures
python3 conformance/build.py                  # regenerate carts + goldens
```

## Running it against your player

Your player is a command. The runner substitutes two placeholders and runs it
once per scene:

- `{cart}` — the cart folder to run
- `{out}` — where to write the frame

Write **either** a 76800-byte raw dump of the framebuffer (one byte per pixel,
palette indices, row-major from the top-left) **or** an 8-bit indexed PNG. The
raw form exists so a C or firmware implementation needs no image library at all
— `fwrite(framebuffer, 1, 320*240, f)` is a conforming adapter.

```
python3 conformance/run.py --player "./build/moyplay --headless --dump {out} {cart}"
```

Every cart is one static frame: `_draw` replays a fixed sequence and nothing
moves, so it does not matter which frame you capture. No `rnd()`, no `time()`,
no input — see the note below.

## Two suites, and why

**This suite tests a RASTER.** The scenes are recorded verb traces, so what they
check is what SPEC.md 6, 7.1 and 7.2 say each verb lights up.

**`examples/verbs.moy` tests a HOST.** It is a real cart exercising the API
through Lua, including the parts a trace cannot reach — the tick model, input
edges, the sandbox ceiling.

An implementation needs both, and the raster one is reachable *first*: a trace
replayer is about forty lines in any language, so a port can check its
rasterizer long before it has a Lua VM wired up. Conformance should be something
you reach early, not only at the end.

## What is in the box

```
scenes.py            the scenes, as Python calls against a Canvas
trace.py             recorder, replayer, and the Lua cart emitter
build.py             regenerates traces, carts and goldens (with self-checks)
run.py               the runner and the player protocol
player.mjs           runs a cart through the shipped WebAssembly player, headless
parity.py            moycore vs the reference implementation, byte for byte
carts/<name>.moy/    a real cart per scene -- what your host runs
traces/<name>.json   the portable verb trace -- what a port replays
golden/<name>.png    the golden frame (indexed PNG: the framebuffer itself)
golden/hashes.json   sha256 per frame, plus the suite manifest
```

| scene | what fails here and nowhere else |
|---|---|
| `primitives` | every core verb, plus 1×1 rects, r=0 and r=1 circles, zero-size rects |
| `edges` | clipping — a host that clamps instead of clipping, or wraps a row |
| `text` | the whole printable range at 8px fixed pitch |
| `text_bytes` | bytes outside 0x20-0x7F draw nothing and still advance 8px; a two-byte UTF-8 character takes **two** cells |
| `camera_clip` | `clip` is **screen** space, applied after `camera`; clipping in world space passes both features separately and fails this |
| `pal_palt` | draw-time remap and sprite transparency together; `pal` must not touch pixels already drawn |
| `sprites` | flips, integer scales, colorkeys, out-of-range tile ids, sprites under camera and clip |
| `tilemap` | `map()` regions, offsets, scale, colorkey, and a region starting out of range |
| `provisional` | SPEC.md 6.1 verbs — **not counted**, SPEC.md 11 excludes 6.1 until it settles |

## Provenance

The goldens are rendered by **moycore**, and the WebAssembly player SPEC.md 11
names as the tiebreaker **agrees with them on all 7 core scenes, pixel for
pixel**:

```
python3 conformance/run.py --player "node conformance/player.mjs {cart} {out}"
```

`player.mjs` boots the shipped player headlessly in plain node — no browser, no
npm — and rasterizes its command stream through the page's own JavaScript
replayer, which it extracts from `runner/index.html` at run time rather than
vendoring (so there is no copy to drift).

That agreement is worth more than a provenance note, because the JS replayer is
the only **independent** implementation in the project. moycore was extracted
from the reference console's rasterizer, so `parity.py` proves the extraction
faithful but cannot catch a bug that was always in it. The page's replayer is
hand-written JavaScript sharing no code with either — so where it agrees, the
agreement means something.

### What running it found

Exactly 200 pixels differed on every scene: a 20×10 box at (299, 229). That is
`runtime/perf_hud.py`'s FPS chip, drawn by the console into the cart's *own*
raster. A golden frame must not contain an FPS counter, and neither should
somebody's published web export. Fixed upstream — the player now takes
`hud=False` and spec bundles pass it; `MOY_HUD=1` forces the chip back on and
reproduces the 200 pixels exactly.

It also found `sspr` rejecting the 10-argument form SPEC.md 7.1 gives it — a
cap of 8 in the Lua binding, so the full form had never worked on *any* host,
boards included. Fixed upstream; `provisional` now matches too, which puts 8 of
the 9 scenes in agreement.

And it found `print` unable to carry any byte past ASCII: a cart doing
`print("\255")` — legal under §6, which draws nothing for that byte but still
advances a cell — killed the whole frame with a `UnicodeError`, on every
moy_lua host including the boards. That took the spec settling on bytes plus
four coordinated fixes (the Lua bridge handing back a byte string, a wire form
that can carry it, a replayer that reads it, and both fonts walking bytes).
`text_bytes` is a core scene as a result.

**All nine scenes pass on the player**, `provisional` included — so the §6.1
verbs agree too, even though §11 does not count them yet.

## And on real silicon

The suite runs on an ESP32-P4 through moybyte's `tools/p4_conformance.py`, which
speaks the same player protocol — it uploads a cart over serial, runs it through
the launcher, and reads the RGB565 framebuffer back off the board:

```
python3 conformance/run.py --player \
  "python3 /path/to/moybyte/tools/p4_conformance.py {cart} {out}"
```

**All nine scenes match there too.** That is the tier where the C `moy_gfx`
kernel, the RGB565 framebuffer and §1.1's memory floor actually live, and it had
never been checked against the spec before.

Its first run — against firmware flashed a few days earlier — failed exactly two
scenes: `text_bytes` and `provisional`. Those are the two bugs the web player had
turned up, both in shared code, so the prediction had been that both were on the
boards too. The board run turned that prediction into a measurement, and
reflashing closed both.

So four things now agree on every scene: moycore, the reference console's own
rasterizer, the web player's JavaScript replayer, and an ESP32-P4.

## Determinism, and one hole in it

Scenes use no `rnd()`, no `time()` and no input, so a golden is reproducible by
construction.

`rnd()` is not merely avoided — it *cannot* be used. **SPEC.md 9 defines its
range but not its sequence**, so two conforming hosts can disagree on every
random number and both be right. Either the spec pins a generator or the suite
forbids `rnd()` permanently. Right now the suite forbids it and the spec is
silent, which is a decision waiting to be made rather than one that has been.

## Adding a scene

1. Write it in `scenes.py` and add it to `SCENES`.
2. `python3 conformance/build.py` — it verifies the recorded trace reproduces
   the scene, that every verb is in the published arity table, and that the
   generated cart loads.
3. **Look at the PNG.** A golden nobody has looked at is a record of what the
   code did, not of what the spec says.
