# Proposal: PICO-8's memory map for ported carts — measured on glass

**Status: landed as `libmoy/src/moy_p8.c`** — an opt-in machine a host opens
with `moy_p8_open`, not a SPEC.md verb; every libmoy host carries it, and
`libmoy/test/p8mem.moy` asserts every mirrored region both ways. It exists
because `p8-tic80-verb-gaps.md` filed `peek`/`poke`/`memcpy`/`memset` under "by
design, never" and SPEC.md §15 calls reaching pixels through a per-pixel
binding "dead at any VM speed", and both were arguments rather than
measurements. This file is the measurement that decided otherwise, and the
design it forces.

## The question

A PICO-8 cart is written against a machine: 64 KB of memory where the sheet,
the map, the flags, the draw state and the screen all have addresses, and the
community's idioms lean on that — palette fades by `memcpy` into `0x5f00`,
screen-to-sheet copies to bake a texture, per-pixel lighting by `peek`/`poke`
over `0x6000`. The p8 port shim gives those verbs a sparse Lua table instead:
bookkeeping works, the machine does nothing. Can a Lua cart on the reference
hardware have the real map, and what does a byte cost?

## What a byte costs — the binding floor

`Mem Bench Lua`, a self-timing cart (adaptive batch, best of five, `time()` at
millisecond resolution, reported through `pmem`), on each board's shipping
clock. Nanoseconds per operation, loop overhead included; the last two columns
are what a full PICO-8 screen of bytes (8,192) costs per frame.

| shape of one access | P4 (RISC-V, 360 MHz) | S3 (Guition / T-Deck, 240 MHz) | 8 KB screen, P4 | 8 KB screen, S3 |
|---|---|---|---|---|
| empty loop iteration | 91 | 156 | 0.7 ms | 1.3 ms |
| Lua table store (`mem[a] = v`) | 396 | 701 | 3.2 ms | 5.7 ms |
| Lua → Lua function call | 732 | 1,220 | 6.0 ms | 10.0 ms |
| **C byte poke, purpose-built binding** | **915** | **1,495** | **7.5 ms** | **12.2 ms** |
| same, with region dispatch (screen/sheet/map/pal/camera) | 1,037 | 1,586 | 8.5 ms | 13.0 ms |
| C byte peek (raw / with dispatch) | 930 / 1,113 | 1,525 / 1,739 | 7.6 / 9.1 ms | 12.5 / 14.2 ms |
| `pmem(i, v)` (libmoy's own C-array verb) | 1,708 | 2,807 | 14.0 ms | 23.0 ms |
| `pix(x, y, c)` through libmoy's binding | 2,136 | 3,601 | 17.5 ms | 29.5 ms |
| the shim's `poke` today (sparse table + `fl()` + `select`) | 7,934 | 12,451 | 65 ms | 102 ms |
| the shim's `peek` today | 3,417 | 5,493 | 28 ms | 45 ms |
| the shim's `pset` today | 6,591 | 10,498 | 54 ms | 86 ms |
| `memcpy` of 8 KB into the screen, one call (resolved per byte) | 1.7 ms | ~2.3 ms (est.) | 1.7 ms | ~2.3 ms |
| `memcpy` of 16 bytes into the draw palette (16 `pal`+`palt` write-throughs) | 4.1 µs | ~7 µs (est.) | — | — |
| `rect` 128×128 fill, one call | 49 µs | 61 µs | — | — |

Three readings, each load-bearing:

- **The floor is the Lua call, not the C.** A purpose-built C byte poke costs
  ~180 ns more than a Lua function call on the P4. The registry lookup and the
  float round-trip in libmoy's generic binding are the difference between 0.9
  and 2.1 µs; a memory verb should not go through them.
- **The shim's fallback is the expensive path.** Routing `poke` to C is a
  **8.7× speed-up** over what a ported cart pays today, not a cost.
- **Bulk is free.** One `memcpy` of a whole screen costs a tenth of a frame's
  worth of pokes; the C fill writes a pixel in 3 ns. Every PICO-8 idiom that
  moves blocks (`memcpy`, `memset`, `reload`) is cheap on this side.

The 64 KB array lives in PSRAM on all three boards (`__moy_mem_region` reports
it), so these are the pessimistic placement. The dispatch rows are the final
design re-measured on the P4; the S3 dispatch rows for peek and the bulk verbs
are the earlier screen-only build's, scaled where marked.

## What real carts do with it

The import corpus as it then stood -- twelve carts -- run 900 frames each on
the desktop MicroPython build with the shim's memory verbs counting
themselves, a scripted button masher on the sticks. Per-frame means; `max` is
the busiest frame.

| cart | peek/frame | poke/frame | bulk | notes |
|---|---|---|---|---|
| **poom** (title / loading) | 1 | **8,963** | `memcpy` 768 B every frame | pokes an 8 KB title image into `0x6000` byte by byte, then `memcpy(0, 0x6000, 8192)` to bake it into the sheet |
| **pico off road** | **2,115** (max 2,310) | **1,094** (max 1,194) | — | the car's shadow: `poke(scanline+x, peek(0x4300 | peek(scanline+x)))` per screen byte under the car, a darkening LUT in user RAM |
| celeste classic 2 | 249 (max 1,808) | 0 | — | level data in `0x4300`; `peek2(0x5f28)` reads the camera |
| low mem sky | 0 | 0 | screen→sheet copies on level change | 168 `pset`/frame |
| dungeons & diagrams, petal quest, mossmoss | ≤ 3 total | | | registers: mouse `0x5f2d`, palette persist `0x5f2e`, btnp repeat `0x5f5c` |
| bunny survivor, crimson night | 0 | 0 | | |
| dank tomb, nimudazus, terra | — | — | — | not counted: the first two failed to load on the shim as it then was, terra busy-loops in the harness |

At the measured floor, the busiest carts' memory traffic per frame:

| cart | P4 | S3 | today's shim, P4 |
|---|---|---|---|
| poom title (8,963 pokes + one 768 B copy) | 9.5 ms | 14.5 ms | 71 ms (and the image never appears) |
| pico off road (3,209 ops) | 3.4 ms | 5.3 ms | 15.9 ms (and the shadow never appears) |
| celeste 2 (249 peeks) | 0.2 ms | 0.4 ms | 0.9 ms |

A PICO-8 frame at 30 fps is 33 ms. Nothing in the corpus spends more than a
quarter of it on memory at the C floor, on either board class.

**On glass, the same carts ported both ways and run on the P4** (`p4_perf`,
PERF DIAG on, median of the settled samples, the cart left on its own screen):

| cart | sparse-table shim | C memory map | where the time went |
|---|---|---|---|
| pico off road | 20 fps, render 39 ms | **25 fps**, render 31 ms | the shadow loop's 3,200 ops a frame, and the shadow now draws |
| poom (loading screen) | 3 fps, logic 297 ms | **5 fps**, logic 178 ms | 9,000 pokes a frame went from ~71 ms to ~8 ms; the other ~170 ms is the cart decoding its title image with `ord()` per byte and 128 `sspr` columns — Lua, not memory |
| celeste classic 2 | 62.5 fps | 63 fps | 250 peeks a frame were never the problem |

poom's row is the honest one: the memory map removes the memory cost and
leaves the tier's own speed, which is #67's problem, not this proposal's.

## The design the numbers force

A **flat 64 KB byte array in C is the truth**, and the console's objects follow
it. Every region that has a console object behind it is kept in step on the
write; the screen has no copy of its own — it reads and writes the canvas:

| region | on write | on read |
|---|---|---|
| `0x0000–0x1fff` sheet, 4bpp | the byte, plus two sheet pixels (`0x1000+` also map rows 32–63) | the byte |
| `0x2000–0x2fff` map rows 0–31 | the byte, plus the cell (console cells hold tile + 1) | the byte |
| `0x3000–0x30ff` flags | the byte (seeded from `__gff__`) | the byte |
| `0x5f00–0x5f0f` draw palette | `pal(i, v & 15)`, `palt(i, v & 0x10)` | the byte |
| `0x5f20–0x5f2b` clip, camera | canvas clip / camera | canvas clip / camera |
| `0x6000–0x7fff` screen, 4bpp | two canvas pixels through the wire table, raw index (no draw-pal remap, as PICO-8) | two canvas pixels, reverse-mapped |
| everything else | the byte | the byte |

`memcpy`/`memset` move bytes with `memmove` and then apply the destination
range's side effects; a copy whose *source* is the screen first pulls those
bytes out of the canvas. The array is seeded at cart start from the sheet and
the map, so `peek(0)` reads the art and a cart that uses map memory as
scratch — `pico off road` does — reads back exactly what it wrote, in one
encoding. (Routing only `0x2000` to the console map through the sparse table
was tried the same morning and reverted; the failure was the seam between two
stores, not the address.)

In the shim, `peek`/`poke`/`peek2`/`poke2`/`peek4`/`poke4`/`memcpy`/`memset`,
and `reload`/`cstore` against a ROM snapshot of the seeded image (`pico off
road` streams its tracks out of map ROM with partial `reload`s, which is why
its race drew over the title before), go straight to the C verbs when the host
has them, probed nil-safe like
`__moy_map_masked`; `sget`/`sset` become sheet-memory reads and writes (so an
`sset` is what `spr()` draws next frame — the old "approximation" is gone), and
`mget`/`mset` read and write the map bytes. A host without the extension keeps
the sparse table.

Thirteen region checks (seeding, screen both ways, map write-through, shared
rows, camera read-back, full-screen `memset`, screen→sheet copy, palette
write-through, bounds) pass against the compiled module on the desktop build.

## What this does NOT reopen

**SPEC.md §12.6 stands.** The p8 screen here is the *shim's* virtual 4bpp
memory, resolved through the palette and the wire table into whatever the host's
canvas is — the host's pixel format never reaches the cart, which is §15's
contract ("a framebuffer in the cart's own memory, never the host's") at 128×128
in Lua. And §12.6's cost claim survives at the console's own size: 76,800
pokes a frame is 69 ms on the P4. A per-pixel effect on the full canvas stays a
compiled-tier (§15) problem; a per-pixel effect on a PICO-8 screen is 7.5 ms.

## What it still does not give a PICO-8 native

None of these are memory questions; each is a raster or shim feature, priced
separately:

- Bitplane masks `0x5f5e`, the sheet/screen remaps `0x5f54`/`0x5f55`, the
  64×64 mode `0x5f2c`, custom fonts `0x5600`. (The screen palette `0x5f10` and
  `fillp` were on this list; both are SPEC.md verbs now.)
- **sfx/music memory** `0x3100–0x42ff`: the audio model is the imported
  `sounds.json`; a cart that synthesises sound by poking sfx RAM plays the
  imported sound instead.
- GPIO/serial `0x5f80+`, `extcmd`.

## The double-float route, measured and closed (2026-09-02)

The cheap way to PICO-8's 16.16 bit tricks would be `lua_Number` as a double:
53 bits of mantissa hold a 16.16 value exactly, so the fixed-point bitwise
shim reverted in moybyte cb08e59 becomes correct with a one-line
`luaconf.h` change. Both reference boards have single-precision FPUs, so
every double op is soft-float. Same firmware otherwise, 32-bit integers kept,
Mem Bench Lua's arithmetic rows and pico off road's race, before and after:

| | P4 float → double | T-Deck float → double |
|---|---|---|
| `x * k` | 205 → 465 ns (2.3×) | 381 → 839 ns (2.2×) |
| `x / k` | 190 → 1,037 ns (5.5×) | 587 → 2,685 ns (4.6×) |
| `x + k` | 209 → 465 ns | 381 → 610 ns |
| `sin` + `cos` | 3.3 → 18.1 µs (5.5×) | 5.9 → 20.5 µs (3.5×) |
| 2D rotate (4 mul, 2 add) | 854 → 2,624 ns (3.1×) | 1,647 → 3,967 ns (2.4×) |
| `pix()` through the binding | 2.1 → 3.4 µs | 3.7 → 4.6 µs |
| pico off road, four cars on the grid | 14.5 → 12.5 fps, render 48 → 61 ms (+27%) | 7 → 6 fps, render 95 → 130 ms (+37%) |
| pico off road, title | 23 → 19 fps | 12.5 → 11 fps |

A quarter to a third of a float-heavy cart's frame, on a tier that is already
the bottleneck, and every moy cart would pay it too, since it is one VM. The
route is closed. What remains for the 16.16 class is a fixed-point VM for
imported carts (z8lua: Lua 5.2.4, MIT, fix32 with PICO-8's overflow
semantics, the dialect built in), which is integer arithmetic and would not
carry this tax -- but it is a second VM in the image and its own project.

## What landing it took

The map moved out of the reference console's `modmoycore.c` prototype into
`libmoy/src/moy_p8.c`, so every host that links libmoy has it and the desktop
simulator's twin is the same C rather than a second implementation to keep in
step.

One gotcha from the measurement sessions, because it invites the wrong
conclusion: three carts once failed at load on the Guition with Lua's `not
enough memory`, and a reflash cleared it. That was the board's state after six
100 KB serial pushes with no reset, not the carts.
