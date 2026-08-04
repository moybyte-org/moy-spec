# The conformance suite

> SPEC.md 11: *An implementation conforms when it runs the conformance suite and
> produces pixel-identical output.*

This is that suite. Eight scenes, seven of them counted; each is a real moy cart
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
| `text` | the printable range, then bytes outside it (draw nothing, still advance 8px) |
| `camera_clip` | `clip` is **screen** space, applied after `camera`; clipping in world space passes both features separately and fails this |
| `pal_palt` | draw-time remap and sprite transparency together; `pal` must not touch pixels already drawn |
| `sprites` | flips, integer scales, colorkeys, out-of-range tile ids, sprites under camera and clip |
| `tilemap` | `map()` regions, offsets, scale, colorkey, and a region starting out of range |
| `provisional` | SPEC.md 6.1 verbs — **not counted**, SPEC.md 11 excludes 6.1 until it settles |

## Provenance — read this before trusting a golden

These goldens are rendered by **moycore**. SPEC.md 11 makes the **WebAssembly
player** the tiebreaker, and re-basing the goldens on frames captured from it
needs a browser harness that does not exist yet.

That is a real gap, and it is narrower than it sounds: `conformance/parity.py`
shows moycore byte-identical to the reference console's rasterizer, which is the
code the player is built from. So these frames *should* already be the player's
frames. The day the harness lands is the day "should" becomes "are".

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
