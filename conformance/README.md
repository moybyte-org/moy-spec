# The conformance suite

> SPEC.md 11: *An implementation conforms when it runs the conformance suite and
> produces pixel-identical output.*

This is that suite. Twenty scenes, every one of them counted; each is a real moy cart
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

Write **either** a 76800-byte raw dump of the canvas -- one byte per pixel,
palette indices, row-major from the top-left; since both palettes compose as
pixels are drawn (SPEC.md 6) this is also the frame as shown -- **or** an 8-bit
indexed PNG of the same. The
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
edges, the host-dependent core verbs, the 3D verbs. It is played and looked
at, not diffed: there is no golden for it.

An implementation needs both, and the raster one is reachable *first*: a trace
replayer is about forty lines in any language, so a port can check its
rasterizer long before it has a Lua VM wired up. Conformance should be something
you reach early, not only at the end.

**Neither of them tests the SPEC.md 4.1 sandbox**, which SPEC.md 11 also
requires of a conforming host. No scene reaches for `io` and `verbs.moy` does not
either, so a player can pass everything here with its sandbox wide open. The one
place that check exists is a CI step over libmoy
(`.github/workflows/libmoy.yml`, "The SPEC.md 4.1 sandbox holds": seven reaches
— `io`, `os`, `require`, `load`, `debug`, `collectgarbage`, `package` — each of
which must make `run_cart` fail; `coroutine` is inside the sandbox and is
asserted PRESENT by `libmoy/test/core_verbs.moy` instead). That covers this
repository's C core and nothing else. Putting it in the suite means teaching the
runner to assert that a cart *fails*, which is a different protocol from "write
me a frame" and has not been designed.

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
wasm_run.py          the compiled-cart runner (below)
wasm_scenes.py       the compiled-cart scenes' twins
wasm/<name>.moy/     a compiled cart per scene, its module as WAT
wasm/golden/         their RGB565 goldens
covers/              cover files and the verdict a reader must reach (below)
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
| `oval` | `oval` / `ovalb` at every box shape the walk branches on, the tiny sizes, zero and negative sizes, edges, camera, clip, pal — and the outline over its own fill, which must ring it exactly |
| `fillp` | holes untouched vs. holes in a second colour, the cell's phase under a moved camera and a clip, all nine shape verbs — and `pix`, `print`, a sprite and a `map` drawn with a pattern live, which must come out solid |
| `flags` | `map(..., layers)` against tile flags from `flags.moyflags`, an `fset` that changes the next map, a mask nobody carries, under scale and camera |
| `layer_left` | `draw_layer` asked past the left edge of a layer wider and shorter than the screen: the camera clamps to 0 on both axes, and the rows below the layer keep the backdrop. A host that repeats the edge, wraps, or fills fails here |
| `layer_right` | past the right edge and above the top, a corner: x clamps to layer − screen, y to 0 |
| `layer_top` | past the top of a layer taller and narrower than the screen: the columns right of the layer keep the backdrop, and every row lands at the screen's stride, not the layer's |
| `layer_bottom` | past the bottom and left of the left, a corner: y clamps to layer − screen, x to 0 |
| `layer_small` | a layer narrower and shorter than the screen, asked for past its far corner, under a screen camera, clip and pal that `draw_layer` must ignore |
| `screen_pal` | `pal(c0, c1, 1)` composes after the draw palette for pixels drawn from then on, a pixel already drawn does NOT move, `pal()` resets both; a player that applies it as a pass over the finished frame fails here |
| `sheet` | `sset` then `spr`/`sspr`/`map` of the edited tile, the 0–15 mask, writes off the sheet; the scene restores its own edits first, since a second frame sees the first frame's sheet |
| `provisional` | SPEC.md 6.1's `tri` / `trib` / `sspr`. Counted since core 0.3; the name is kept because implementers cite it |
| `provisional_tline` | SPEC.md 6.1's `tline`: the map sampled through 16.16 texture steps. Counted since core 0.3 — and the scene that caught a real board failing by 2773 pixels (below) |

## Provenance

The goldens are rendered by **moycore**, and the WebAssembly player SPEC.md 11
names as the tiebreaker agrees with them on every scene:

```
python3 conformance/run.py --player "node libmoy/port/wasm/conform.mjs {cart} {out}"
```

That runs the shipped `runner/moy.wasm` — libmoy compiled by emscripten — under
plain node, no browser and no npm, and dumps its index framebuffer.

### The independent check, and its loss

**This used to be worth more than a provenance note, and now it is worth less.**
Until 2026-08, the web player was a MicroPython build of the reference console
that rasterized nothing itself: it emitted draw commands and the *page*
rasterized them in hand-written JavaScript. `conformance/player.mjs` extracted
that replayer out of `runner/index.html` at run time and rendered the scenes
through it.

That made it the project's only **independent** implementation. moycore was
extracted from the reference console's rasterizer and libmoy is a transcription
of moycore, so all three share one lineage: `parity.py` proves the extraction
faithful and the goldens prove the transcription faithful, but neither can catch
a bug that was in the original. The JS replayer shared no code with any of them,
so where it agreed, the agreement meant something.

Rebuilding the player from libmoy deleted it. The page no longer rasterizes —
that is the point, and the reason the bundle went from 1 MB to under a third of
that — so there is no second raster in it to disagree with the first.

**Getting it back is a small, well-shaped job, and it is the one thing this suite
is missing**: a replayer of `traces/<name>.json` written from SPEC.md rather than
from moycore, in any language. The traces are published for exactly that, and
this file claims above that a trace replayer is about forty lines. Nobody has
written it. Until somebody does, every "five agree" here means five descendants
of one raster, and this section is an accounting rather than a boast.

### What the replayer found while it lasted

Three bugs, which is the whole argument for independence and why the history stays.

**An FPS chip in the goldens.** Exactly 200 pixels differed on every scene, a 20×10
box at (299, 229): the reference console's perf HUD, drawn into the cart's *own*
raster. Nobody's golden frame — or published web export — should contain one. Fixed
upstream, and moot for the current player, which has no console around the cart to
draw a chip. It still took a second implementation to see it.

**`sspr` had never accepted its full form.** The 10-argument signature SPEC.md 7.1
gives it hit a cap of 8 in the Lua binding, so it had never worked on *any* host,
boards included.

**`print` could not carry a byte past ASCII.** `print("\255")` — legal under §6, which
draws nothing for that byte and still advances a cell — killed the frame with a
`UnicodeError` on every moy_lua host, boards included. Fixing it took the spec settling
on bytes plus four coordinated changes: the Lua bridge handing back a byte string, a
wire form that can carry it, a replayer that reads it, and both fonts walking bytes.
`text_bytes` is a core scene because of it.

By the end every scene passed, the §6.1 ones included even though §11 does not count
them. The player built from libmoy passes them too; it just is not an independent
witness to it.

## And on real silicon

The suite runs on an ESP32-P4 through moybyte's `tools/p4_conformance.py`, which
speaks the same player protocol — it uploads a cart over serial, runs it through
the launcher, and reads the RGB565 framebuffer back off the board:

```
python3 conformance/run.py --player \
  "python3 /path/to/moybyte/tools/p4_conformance.py {cart} {out}"
```

**Every scene the suite then held matched there too.** That is the tier where
the C `moy_gfx` kernel, the RGB565 framebuffer and §1.1's memory floor actually
live, and it had never been checked against the spec before.

Its first run — against firmware flashed a few days earlier — failed exactly two
scenes: `text_bytes` and `provisional`. Those are the two bugs the web player had
turned up, both in shared code, so the prediction had been that both were on the
boards too. The board run turned that prediction into a measurement, and
reflashing closed both.

So five runs agreed on every scene the suite held before the `layer_*` scenes:
moycore, the reference console's own rasterizer, libmoy, libmoy again as the
WebAssembly player, and an ESP32-P4.
**Five runs, one lineage** — and until 2026-08-07 that was not quite true, which
is the interesting part. The board ran `moy_gfx`, a hand transcription, the only
raster in the set that could disagree by accident rather than by inheritance.
That day six of its verbs (`tri`, `sspr`, `tline`, `circ`, `circb`, `line`)
became calls into libmoy, because on-glass conformance had just caught
`provisional_tline` failing on the board by 2773 pixels while passing on the
host — a transcription bug only the board could see. Later the same day `print`,
`blit_map` and the sprite path followed, on a re-measurement that overturned the
numbers which had kept them out (that repo's `libmoy/UPSTREAM.md` has the table).

The right trade, and it closes the loop the wrong way round: the fix for "the
transcription drifted" is to stop transcribing, and the price is the last
independent witness. What `moy_gfx` still owns is its compositor — viewport-aware
fills, the scroll blit, async DMA, the window composite — which has no
counterpart here to disagree with. So the replayer above is the outstanding job.

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

## Compiled carts: `wasm_run.py`

Everything above judges the index raster through Lua carts. A `"runtime":
"wasm"` cart (SPEC.md §16) is
judged by a suite of its own under `wasm/`: compiled carts whose modules are
committed as WAT source (`tools/wat.py` assembles them), and whose goldens are
**RGB565 frames** (§16.11), because a palette blit's
256 colours do not fit a palette-index golden. The PNGs in `wasm/golden/` are
those frames with each channel's bits repeated, so each is a picture and reduces
back to its words exactly; `wasm/golden/hashes.json` holds the words' sha256.

```
python3 conformance/wasm_run.py                        # every host built here
python3 conformance/wasm_run.py --hosts harness,desktop,browser
python3 conformance/wasm_run.py --player "CMD"         # yours
python3 conformance/wasm_run.py --build                # re-render the goldens
```

The player protocol is §11's with a compiled cart's frame: run the cart's two
ticks with the clock stopped and nothing pressed, write the last frame it
**finished** to `{out}` as W × H little-endian RGB565 words, and exit 0. The
cart's written files (§16.12) live in the folder `{files}` names, empty for a
scene and kept for the scene that runs the same cart again. A tick
that traps exits non-zero with the last whole frame written; a refused cart
exits non-zero with nothing written. `wasm_run.py`'s docstring is the full
statement.

| scene | what fails here and nowhere else |
|---|---|
| `blit` | a 256-entry palette handed over with the frame; the frame replaces the whole screen whatever the camera, clip, pal and target are, and a HUD drawn after it lands on top through them |
| `blit565` | a direct-colour frame shown word for word: the byte order is the spec's, never the panel's |
| `write` | the cart's writable files on a fresh store: a written copy read before the shipped one, every path `write` must refuse (undeclared, malformed, past 64 bytes, another case), a write past 1 MiB, an empty file, `erase` twice, and `list` in bytewise order with "Case" and "case" apart and a short buffer answering the whole length |
| `write_again` | the same cart run again on the store the first run left, as after a restart: everything written is there, and an erased copy gives the shipped file back |
| `read` | the cart's own files: sizes, short reads, reads at and past the end, a file in a subfolder — and 0 for an absent name, a folder, and every name the rule refuses. A host that opens a folder as if it were a file answers garbage for it, which is how this scene's folder question came to be asked |
| `target` | drawing into a layer and back, a layer's own camera persisting across hooks, `pix` read back from it, and its pixels kept between frames |
| `verbs` | every ordinary verb through the binding at the import table's arity: the sentinel forms, `camera`'s out pointer, read-backs feeding colours, a sheet and map written with `sset` and `mset`, over a frame blitted through the cart's own palette with indices past 63 |
| `primitives` | §11's scene of that name as a compiled cart: the same trace, through the binding, held to that scene's golden reduced to RGB565 |
| `layer_left` … `layer_small` | §11's layer scenes the same way: the layer made in `_init`, drawn into through `target`, composited by `draw_layer` |
| `par` | the frame's rows as eight items: the same frame whether a host ran them on several cores or one after another, each item on the stack the rule gives it and the caller's stack pointer put back |
| `trap` | a trap in the second frame: the player shows and writes the first |
| `par_trap` | a trap in one of `par`'s items, in the second frame: it traps the cart, whichever core the item ran on |

Every scene is also held to `moy check`, and the refusal fixtures — libmoy's
shape fixtures in `libmoy/test/wasm/` and `wasm/too_big.moy`, a well-formed cart
asking for 4 GiB — must be refused by every host.

**Provenance.** The goldens come from the twins in `wasm_scenes.py`: a blit's
palette and bytes applied by hand from §16's rules, and every ordinary
verb drawn by moycore, the raster the index goldens come from. `verbs`,
`primitives` and the layer scenes are data rather than WAT — `wasm_scenes.VERBS`
and their `traces/*.json` — and `--build` writes their modules from it, so the
cart and its twin cannot drift.

**The hosts.** Three in this repository run it: libmoy's WAMR harness
(`libmoy/build/wasm_test play`), the desktop player (`moy-play --dump`, WAMR's
interpreter inside the SDL2 port) and the web player (`conform.mjs`, the cart a
sibling module on node's engine, its imports adapted onto the same C). Two
engines, one binding: they agree on every scene, and that is a statement about
`libmoy/src/moy_wasm.c` and about the adapters, not an independent witness to
§16 — the lineage caveat above applies here too.

## Covers: `covers/`

A host that shows covers reads `cover.png` (SPEC.md §3.6), and `covers/` is
that reader's suite: PNG files, and `expected.json` giving the verdict on each
— `cover`, with the sha256 of its 128 × 128 pixels as R, G, B bytes, row-major
from the top-left, or `ignored`. Hand your reader each file's bytes and compare.
No player and no cart are involved.

The covers take both colour types through every scanline filter, singly and
mixed, with palettes of one and 256 entries, ancillary chunks on both sides of
the image data, the zlib stream split over several `IDAT` chunks, stored deflate
blocks, and a file of exactly 65,536 bytes. The ignored files are the profile's
edges — 127 × 128, 128 × 129, 1 × 1, 512 × 512, 65,537 bytes, interlaced,
16-bit, RGBA, greyscale, 4-bit indexed, `tRNS` — and the broken ones: image
data cut short, a reserved deflate block type, filter type 5, a pixel past the
PLTE, an indexed file with no PLTE, and a file that is not a PNG.

```
python3 conformance/covers/build.py            # rewrite the files
python3 conformance/covers/build.py --check    # expected.json is current
make -C libmoy cover-test                      # moycore's reader against them
```

`build.py` writes each file chunk by chunk, so a vector stays the case its name
says, and takes each cover's hash from the picture it drew rather than from a
decoder. The files hold a zlib stream, and zlib's output differs between
versions, so a rebuild elsewhere may differ in bytes while saying the same
thing; the verdicts and hashes do not.
