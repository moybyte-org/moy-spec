# Proposal: `runtime: "wasm"` — the compiled-cart binding

**Status: binding candidate. Not part of core 0.3.** SPEC.md §15 records the
doctrine and names `"wasm"` the reference console's vendor runtime until this
document is promoted; this document is the ABI it points at. Every number in it
is measured, not estimated — the evidence run is a 6502 interpreter core,
line-faithful in Lua and C with identical cycle counts out of every runtime, on the
reference console's RISC-V board at its shipping clock (moybyte#158,
`experiments/wasm_aot`, 2026-07-27), and since 2026-09-24 on the Xtensa floor board
as well (same issue, same core).

What this document decides is the contract a cart and a host meet at: the cart,
the module shape, the import table and how every verb crosses the boundary, the
framebuffer, the asset read, the sample stream, memory and traps. What is still
open is listed at the end, and none of it reopens the contract. Three executable copies of the
contract sit beside it, each tested against the others:

- **`wasm-imports.json`** — the import table, one row per import: its wasm type,
  its WAMR signature string, the SPEC.md section of its verb, and the notes that
  say how the verb's Lua forms become one wasm function. The prose below is the
  table's argument; the JSON is the table.
- **`libmoy/src/moy_wasm.c`** — the table as C, built only when asked for, over
  WAMR or under a JavaScript embedder's own engine (libmoy's README says how).
- **`moy check`** — a wasm cart's module against the table, its manifest and the
  rules below.

## Why a second binding, and why this one

The verb table is the console (SPEC.md §15); Lua is its first binding, not its
definition. The second binding exists for the work the first cannot hold:
**step-bounded** rendering — voxel terrain, general textured 3D, per-pixel
effects, emulators — where the cost is the cart's own loop and no verb can absorb
it (SPEC.md §6.1).

A native binary cannot be that binding. The reference lineup alone is already
three instruction sets (Xtensa, RISC-V, x86-64/ARM host), so "compiled cart"
would mean per-board artifacts — the fragmentation every small-console ecosystem
drowns in. WebAssembly is the compilation target every systems language shares,
it is sandboxed by construction (linear memory is bounded; imports are the *only*
capability surface — the verb table literally is the sandbox), and it is one
artifact for every tier including the browser.

**The measured case** (reference hardware, on glass):

| runtime | 6502 instr/s | vs Lua | arithmetic (`spin`) |
|---|---|---|---|
| Lua (the shipping binding) | 0.173 M | 1.0× | 5.2 M ops/s |
| WASM, WAMR fast-interp | 0.188 M | **1.09×** | 12.35 M |
| WASM, AOT (XIP — the *pessimistic* mode) | 2.828 M | **16.3×** | 476 M (**91×**) |

Two conclusions, both load-bearing: **interpreted WASM does not justify a
runtime** — its advantage collapses exactly on dispatch-shaped code, which is
what interpreters and emulators are — and **AOT does**. An interp-only evaluation
would have said no and been wrong.

## The cart

```json
{ "format": "moy-1", "title": "…", "runtime": "wasm", "main": "main.wasm",
  "memory": 64 }
```

`main` names the module, and for this runtime it defaults to `main.wasm`.
`memory` is required: the cart's linear memory in 64 KiB pages (see Memory).
`sources` does not apply — a compiled cart is one module — and a manifest that
lists it is refused the way §4 refuses a broken one. Every other field keeps its
§3.1 meaning, `canvas` and `fps` included, and every asset file is unchanged:
`sprites.moygfx`, `map.moymap`, `flags.moyflags`, `sounds.json`, `config.json`. A
host that does not implement the binding refuses the cart cleanly (§3.1); one that
does loads `main.wasm` — **the `.wasm` is the sole portable artifact**. A
per-architecture compiled form is a host's build product and never appears in a
cart.

Source is welcome beside it — `src/` in the folder, or a `"source"` manifest
field carrying a URL — and never required or verified. The always-readable tier
is the Lua cart.

## Module shape

- **Profile: wasm32, MVP.** No WASI, no threads, no SIMD, no GC proposal. The
  profile is pinned so a 2026 toolchain and a 2030 one produce carts the same
  host runs; extensions to it are a spec revision, not a toolchain default.
- **One linear memory, the module's own**, exported as `memory`, its minimum
  equal to its maximum equal to the manifest's `memory`. Not imported, not
  shared, not 64-bit.
- **Exports:** `_init()`, `_update(f32 dt)`, `_draw()` and `memory` — all four
  required, at exactly those types; an empty hook is an empty function. The host
  calls the three hooks as the §5 tick calls the Lua ones, with `dt` the tick
  period. Any other export is ignored.
- **No start function.** Nothing in the module runs before `_init`.
- **Imports: functions from module `"moy"`, each a row of the import table at
  that row's exact type.** A cart imports only the rows it uses. The Lua build is
  `LUA_32BITS` (§4.2), so the two bindings already share a numeric world; nothing
  widens.
- **No other imports exist.** That sentence is the entire §4.1 sandbox for this
  binding. A module that imports anything else — from another module, a memory, a
  global, a table, a name outside the table, a row at the wrong type — is refused
  before it runs.

A cart author's toolchain is one command, no SDK:

```sh
clang --target=wasm32 -O2 -nostdlib -Wl,--no-entry \
      -Wl,--export=_init,--export=_update,--export=_draw \
      -Wl,--initial-memory=4194304,--max-memory=4194304 \
      -o main.wasm main.c
```

(the two memory sizes are `"memory": 64` in bytes) with a ~50-line `moy_cart.h`
of import declarations (`__attribute__((import_module("moy"),
import_name("cls")))` …) that belongs in this repository once the ABI freezes.
`zig build-exe -target wasm32-freestanding` and Rust's `wasm32-unknown-unknown`
produce the same module with zero setup.

## The import table

**The import table is the verb table.** Every verb the Lua binding installs is
one import of the same name and the same §6–§9 meaning, and five exist because
this binding needs them: `blit` and `blit565` (the framebuffer), `read` (the
cart's own files), `target` (drawing into a layer) and `snd` (the sample
stream). `wasm-imports.json` lists every one; a verb the spec gains is a row
there before it is anything else.

`W` and `H` are not imports. The canvas is the manifest's (§1, §3.1) and a host
runs the cart at exactly that size or refuses it, so a compiled cart knows both
when it is compiled.

## Marshalling — one Lua verb, one wasm function

A Lua verb is dynamically typed, takes optional arguments, overloads by argument
count and returns several values; a wasm import has one fixed type. These rules
close the gap, and every row's notes apply them.

- **Numbers.** `i32` for integers, indices, colours, coordinates and booleans;
  `f32` where the Lua verb takes or returns a fraction (`rnd`, `beep`, `flr`'s
  argument, `_update`'s `dt`). A boolean is `i32` 1 or 0 in both directions, and
  any non-zero argument reads as true.
- **Every argument is passed.** Lua fills an absent argument with a default; a
  wasm call has no absent arguments, so the cart passes the default. The table's
  notes carry Lua's defaults.
- **An overload by argument count is one import at the widest arity**, and the
  narrower form is a sentinel in an argument it omits: a negative value where the
  verb's own values are never negative (`pix`'s colour, the bit of `fget` and
  `fset`, the code of `key` and `keyp`, the index of `pal` and `palt`,
  `sound_stop`'s channel). Where no value is free, a last argument selects the
  form (`pmem`'s `write`). A no-argument reset whose effect is an ordinary call is
  that call: `camera()` is `camera(0, 0)`, `clip()` is `clip(0, 0, W, H)`,
  `fillp()` is `fillp(0, -1)`.
- **Several results** are written as consecutive `i32` at an out pointer passed
  as the last argument, which may be 0 to discard them (`camera`'s previous
  offset, `touch`'s four values).
- **nil is a value the verb could not otherwise return**: 0 for a layer handle
  and for `touch` with no pointer, -1 for an absent `cfg` key. A verb that already
  answers an integer for "nothing" keeps it (`mget`'s -1).
- **Strings are bytes in linear memory, passed as a pointer and a length** — no
  terminator and no encoding, exactly the byte string a Lua string is (§6's
  `print`). A name drawn from a closed set is its index in the order the spec
  lists the set instead: `btn(0, p)` is `btn("left", p)`. A verb that answers a
  string copies it into a buffer the cart supplies and returns its whole length,
  so a short buffer is visible (`cfg`).
- **Layers are handles.** `make_layer` returns a positive `i32` that names the
  layer until the cart ends, or 0 where Lua returns nil. Where a Lua cart calls a
  method, `ly:rect(…)`, a compiled cart points the drawing verbs at the layer —
  `target(ly)` — draws, and points them back with `target(0)`. The verbs `target`
  redirects are exactly the ones a Lua layer answers, a layer keeps its own draw
  state as it does in Lua, and the target is the screen whenever the host calls
  an export. A handle `make_layer` never returned is a trap, as a method call on
  something that is not a layer is an error in Lua. Nothing frees a layer: it
  lives until the cart ends, where Lua's collector may end it sooner.
- **Pointers are offsets into linear memory**, checked on every call; a range
  that leaves the memory is a trap. 0 means "none" wherever a pointer is
  optional, since no toolchain places an object at address 0.
- **`time()` is the clock.** There is no clock import: §9's `time()` answers
  milliseconds since the cart started, which is all a cart needs to measure. It
  paces itself by returning from `_update`, and §5 calls it again.
- **No import blocks.** Every import completes in time bounded by its arguments —
  `read` by its length, `blit` by the frame, `snd` by its count — and none waits
  for input, a timer, the display, the audio output or the network. There is no
  sleep and no vsync wait: a cart waits by returning.
- **`quit()` does not return.** The host unwinds the cart as it would for a trap
  and treats the unwinding as the cart ending itself (§9), with no report.

## The framebuffer contract — `blit`

The measured blocker is not speed but the boundary: a compiled cart reaching
pixels through the `pix` import pays a trampoline per pixel — 76,800 crossings
per frame, dead at any VM speed. The fix is an import that hands over a whole
frame at once:

```c
void blit(i32 frame, i32 pal);   /* frame: W x H bytes in linear memory, one
                                    palette index per pixel, row-major.
                                    pal: 0 for the cart's own palette, or 768
                                    bytes of RGB -- a 256-entry palette
                                    presented with THIS frame */
```

`W × H` is the declared canvas (§1), 76,800 bytes at the default 320 × 240. With
`pal` 0 an index names the cart's §2.2 palette entry, modulo 64; otherwise it
names one of the 256 entries at `pal`. The frame covers the whole screen and
ignores the draw state — camera, clip, both palettes, `palt`, `fillp` — and the
target: like `cls` it composites rather than draws. It is legal only inside
`_draw`, at most once per `_draw` counting `blit565`; a call anywhere else, or a
second one, is a trap. A cart may freely mix `blit` with ordinary verbs; draw
order is call order, so a HUD drawn after the blit lands on top of it.

**The frame stays as blitted until `_draw` returns.** A host may present it
straight from the cart's memory — a panel flush that resolves the palette as
it ships the frame, say — and so read it after the call rather than during it.
A cart therefore leaves the frame it handed over, and its palette, unchanged
for the rest of that `_draw`; from its next hook the memory is its own again.
What the cart draws is the same either way: a verb drawn over the frame, or a
pixel read from it, meets the frame as it was blitted.

A frame a palette blit wrote holds up to 256 colours, which the 64 indices of an
indexed canvas cannot represent, so a host running this binding keeps the screen
in direct colour while a wasm cart runs — the choice §1.1 already allows. What
`pix` reads back from a pixel a palette blit wrote is host-dependent (an index
0–63), and no conformance scene reads one.

**The per-frame palette is deliberate, and it does not reopen §12.1.** That
decision forbids retroactively re-meaning pixels already drawn on a retained
canvas; a `blit` is a complete frame delivered together with its own palette —
nothing is retained, nothing re-meant, and the host's cost is rebuilding a
256-entry LUT per frame, which is noise. What it buys is the entire class of
runtime-palette work the fixed §2.2 table cannot express: palette-driven fades
and flashes, palette cycling (plasma, waterfalls), and — the cases that surfaced
it — emulation and ports. An emulated console's palette RAM changes at runtime,
and a ported engine brings its own: Doom's is 256 entries and a frame uses well
over 64 of them. With 256 entries any game holding 256 or fewer simultaneous
colours maps exactly, fades included. (The NES needs none of this: its 54-entry
master palette is fixed hardware and fits §2.2 as-is. The GB's 4 shades
likewise. Per-scanline palettes remain a bridge deliberately not crossed; above
256 simultaneous, see `blit565` below.)

Measured budget: ~4.6 M pixel-writes/s from AOT code into linear memory against
476 M ops/s of arithmetic — a full-screen software raster lands ~17 ms on the
measured board, inside a 30 fps frame with the geometry effectively free. This
does not reopen §12.6: the cart writes *its own* memory, the host's framebuffer
stays opaque, and hosts keep every freedom of depth, scale and byte order.

Assets stay host-side as well: `spr`, `map` and `sspr` render the cart's sheet and
map as ever, and a cart that wants its files' bytes reads them (`read`, below).

### Full colour — `blit565`, and why it is not the default

256 colours is a palette ceiling, not a hardware one, and it is the wrong
ceiling for content that was never palettized — gradients, shaded 3D,
photographic art — which cannot be submitted through `blit` without the cart
quantizing or dithering it first. So a second submission format, alongside the
first, never replacing it:

```c
void blit565(i32 frame);   /* frame: W x H RGB565 words in linear memory,
                              LITTLE-ENDIAN, row-major -- 153,600 bytes at
                              320 x 240 */
```

Exactly `blit`'s rules: only inside `_draw`, at most once counting `blit`, the
whole screen whatever the draw state, and the result treated exactly as a
§6-drawn frame, freely mixed with ordinary verbs in call order.

**The byte order is fixed by this document, and is not "whatever the panel
wants."** That is the whole difference between a portable contract and a device
one — the moment the submitted layout tracks the display, a cart writes to
*that* framebuffer rather than *a* framebuffer and §12.6 is quietly reopened. A
host with a byte-swapped 16-bit panel swaps; a browser expands to RGBA8888; a
desktop player expands to RGB888. Those conversions are dependency-free
streaming loops and run at roughly copy speed, which is what makes fixing the
order affordable rather than pious. Pinning it also keeps this tier
golden-checkable: a `blit565` frame hashes as deterministically as an indexed
one, so §11 conformance reaches compiled carts without a second mechanism.

**Do not reach for it expecting speed. It is slower on both sides of the
boundary.** Measured on an ESP32-P4 (360 MHz, PSRAM 200 MHz, 256 KB L2, `-O2`),
one rasterizer compiled twice from a single source, differing only in stored
pixel type:

| the cart's own raster | 8-bit indices | RGB565 |
|---|---|---|
| filled rects | 988 µs | 1292 µs (**+31%**) |
| textured scanlines | 6780 µs | 7455 µs (+10%) |
| scaled sprite columns | 7921 µs | 8518 µs (+7.5%) |
| triangles | 4789 µs | 5004 µs (+4.5%) |

Two bytes per pixel is twice the store traffic, and a software rasterizer is
store-bound. Against the ~17 ms full-screen budget above, choosing `blit565`
costs the cart **+0.8 to +5.3 ms** — and it saves the host only ~0.8 ms, the
difference between resolving a palette (1148 µs with a pixel-pair LUT; 2026 µs
with the per-pixel loop both current implementations still use) and copying
153,600 bytes (344 µs). Best case a wash, worst case six times worse. The
palette resolve does not close that gap with more optimization either: every
lookup's address depends on the byte just loaded, so it plateaus around 3× a
copy where a copy has no dependency chain at all.

**On the floor board it is not close.** Same bench, ESP32-S3 at 240 MHz with
octal PSRAM and no L2 — the board a cart is most likely to be too slow on, and
therefore the one that decides:

| the cart's own raster | 8-bit indices | RGB565 |
|---|---|---|
| filled rects | 3226 µs | 10615 µs (**3.3×**) |
| triangles | 9410 µs | 21853 µs (**2.3×**) |
| scaled sprite columns | 18466 µs | 25163 µs (1.4×) |
| textured scanlines | 18275 µs | 20823 µs (1.1×) |

A 32-bit fill store covers four indexed pixels and only two RGB565 ones, and
with no cache to absorb it the wider format is paid in full. The host side
inverts too: with the source half the size, the palette resolve is **cheaper
than the copy it would replace** — 1681 µs against 2483 µs into the panel's
bounce buffer. So on this board `blit565` costs the cart up to 3.3× and saves
the host nothing at all.

The rule that follows: **a cart that could have been indexed should stay
indexed.** `blit565` is for carts whose pixels are inherently direct-color,
where the indexed route would cost a quantization pass rather than save a store.
On the faster board that rule is advice; on the floor board it is close to a
requirement, and a cart that ignores it will be judged on the floor board.

(Floor-board figures are at 80 MHz PSRAM, not the 120 MHz the reference console
ships: that board's flash is not verified for the high-performance mode
`SPIRAM_SPEED_120M` requires, and a 120 MHz build aborts in MSPI timing init.
80 MHz makes external memory dearer than it really is, so the margins above are
generous — but the 3.3× is far outside what a bus-speed correction reaches, and
the internal-SRAM rows do not depend on it at all.)

**Memory.** 153,600 bytes against §1.1's 192 KB cart heap leaves ~40 KB for the
game, which is not a budget. On the floor board it is worse than a budget
problem: with the console's own 76,800-byte canvas resident, a second
153,600-byte buffer **could not be allocated contiguously in internal SRAM at
all** — on an otherwise empty heap, before MicroPython, the Lua allocator's
48 KB floor or the DMA buffers exist. A `blit565` cart there is committed to
external memory for its framebuffer, which is exactly where the 3.3× above
comes from. §1.1's ≈400 KB is a **tier-1 floor**: it exists so
the script tier stays implementable on modest hardware, and it is stated in
terms of a host that owns every pixel. This tier owns none of that — a host
implementing it already carries a WASM runtime, an AOT toolchain, and the
external RAM the module and its linear memory load into. Nothing that can do
those things is short of RAM. **The compiled tier therefore declares its own
floor** rather than bending tier 1's, and `blit565`'s framebuffer is the reason
the number has to move. The Memory section below is how a cart declares its
share and how a host checks it.

## Reading the cart's own files — `read`

```c
i32 read(i32 name, i32 name_len, i32 offset, i32 dst, i32 len);
```

Copies up to `len` bytes of the cart's own file `name`, starting at byte
`offset`, into linear memory at `dst`, and returns how many it copied. With `len`
0 it copies nothing and returns how many bytes remain from `offset` — at offset 0,
the file's size.

`name` is a path relative to the cart's folder: bytes, `/`-separated, every
segment non-empty and neither `.` nor `..`, with no `\` and no NUL. A name that is
absent, or that breaks that rule, reads 0, and so does an offset at or past the
end — so a cart cannot tell a missing file from an empty one, and cannot reach
anything outside its folder. That is as far as §0's "no filesystem access"
stretches: the folder already is the cart. Every file in it is readable, the
manifest and the module included; nothing is writable, and `pmem` (§9) stays the
only state a cart keeps.

It exists because a ported engine needs its own data and the sprite sheet cannot
carry it — Doom reads a 4 MB WAD. The read is synchronous and bounded by `len`: a
host whose carts live on slow storage makes it slow, and never makes it wait on
anything else. A user's own files — a document the cart did not ship — are a
different capability (moybyte#108) and would be a different import, so this one
never widens past the cart's folder.

## Memory — one fixed block, checked before it exists

A compiled cart's memory is one block, sized by its manifest and never grown.
`"memory": N` declares N pages of 64 KiB (65,536 bytes each), and it covers
everything the cart has: its data, its stack, its heap, any frame it blits from.
The module's memory minimum and maximum are both N, so `memory.grow` answers -1,
as wasm specifies, and a cart plans for that rather than trapping on it.

A host checks this **before it allocates anything.** A manifest without
`memory`, or a module whose memory disagrees with it, is refused — §3.1's clean
refusal — before the module is instantiated: never half-loaded, never grown to
fit. So is a cart whose whole load footprint — the declared memory, the module's
code and the engine's working pool — is more than the host can give it, and that
refusal is a plain notice to the player naming both figures, never an error
report or a crash.

**The floor is the floor board's.** The tier's floor is the reference
implementation's floor board's share of its cart-runtime reserve with the runtime
resident, so a compiled cart within it runs on every board of the lineup — the
same no-fragmentation rule §1.1's floor enforces for scripts. A cart above it is
allowed: it runs only on consoles with more memory, and a console that cannot fit
it refuses it at launch with the notice above. Like §1.1's floor it is checkable
before any host sees the cart, and what the check says is a warning that names
the floor, not a refusal: `moy check` reports a manifest above it as running only
on consoles with more memory. A host that cannot give a cart within the floor its
pages is short of the floor, and fixing that is the host's problem, as §1.1 makes
its own floor the implementer's. The figure lands here when it is measured (open
item 8); until then `moy check` carries it as a named constant with no value and
warns about nothing on size.

## Traps

A trap ends the cart the way a Lua error does (§4.3). Whatever makes wasm trap —
`unreachable`, an out-of-bounds access, an integer division by zero, a stack
overflow — traps the cart, and so does everything this document calls a trap: an
import handed a range outside linear memory, a layer handle `make_layer` never
returned, a `blit` outside `_draw` or a second one inside it. The host reports it
— the trap's message, and whatever location the module lets it recover — and
goes back to where the player launched the cart. **The frame the trap interrupted
is never presented**: the player sees the last whole frame, then the report. A
trapped instance is never called again, and a host keeps a trap from passing
silently exactly as §4.3 requires of a Lua error.

`quit()` unwinds the same way and is not a trap (Marshalling).

## PCM audio — `snd`

SPEC.md §8 is a tracker-shaped data model, which is right for authored carts and
useless for an emulated APU or a ported engine's mixer: those produce a sample
stream. So this tier's audio surface is **samples, not the §8 data model** — the
same finding as the framebuffer and the per-frame palette, from a third angle:
this tier programs the console's hardware, not the script tier's abstractions.
The §8 verbs stay in the table, and a cart may use both.

```c
i32 snd(i32 pcm, i32 nframes);   /* pcm: nframes of signed 16-bit mono,
                                    LITTLE-ENDIAN, at 22,050 Hz. Queues what
                                    the host has room for and returns how
                                    many; with nframes 0 it reads nothing and
                                    returns the room */
```

**22,050 Hz, mono, 16-bit.** The rate is the one the reference console's boards
output and PICO-8's own, which §8.3's synthesis is defined at, so on the
hardware tier a stream reaches the speaker unconverted and costs the console
one add per sample. Doom's effects are 11,025 Hz, an exact half. The boards'
speakers carry nothing a higher rate would add, and 44,100 Hz doubles the
cart's mixing and the copy for none of it. Mono because every speaker in the
reference lineup is one speaker and §8.3 mixes to mono; a cart with stereo
sources folds them itself. A browser or desktop resamples to its device, which
is `blit565`'s position again: the format is fixed by this document and the
host converts, never the cart tracking the device.

**The host holds 2,048 frames**, about 93 ms: that many frames the cart handed
over and the output has not yet taken. The cart refills the queue once per
frame, so it has to outlast the gap between two frames with room for a slow
one. The first cart to use it, Doom, draws in the 30s and 40s of fps on the
floor board — 25 to 35 ms a frame, and a WAD read over SD adds 5 (moybyte#158).
2,048 frames is more than two frames at 30 fps before the stream runs dry; half
that is under two, one hitch from a gap, and twice that puts a sound effect a
sixth of a second behind the frame that caused it. The depth is also the most
latency the queue adds. What an output does after it takes frames — a DMA ring,
a browser's audio thread — is its own latency, like a panel's, and does not
count against the 2,048.

**The return value is the clock.** The output drains the queue at its rate and
the cart fills it at its own pace, and neither may assume the other's: a cart
that makes a fixed count per tick drifts against the output, because two clocks
never agree, and starves it or overflows it. A cart that asks for the room
(`snd(0, 0)`) and fills it — or offers what it has and keeps what was not
taken — tracks the output exactly, whatever its frame rate. 0 means the queue is
full for now; nothing blocks (Marshalling).

**Silence drains at the rate.** §8.3 already makes silence a valid rendering, so
a host without audio accepts and drops — and its queue still drains by the
console's clock, 22,050 frames a second, so the cart meets the backpressure it
would meet where the frames are played. A cart that paces itself on the stream,
an emulator syncing to its APU, runs at speed on a silent host. The cart cannot
tell, exactly as with `sfx`.

How the stream meets the console's own sound is the host's. libmoy's
`moy_stream` (`moy_audio.h`) is a queue mixed into the §8 synth's output after
its channels and under its master level, and it is what the reference console
and this repository's players use. A `pcm` range outside linear memory is a
trap, and a negative `nframes` is such a range. Audio has no goldens (§8.3);
what conformance holds is the counts, which a stopped clock makes exact.

## Determinism

WASM is deterministic except NaN bit patterns. The binding pins it with one rule:
**a conforming host may canonicalize NaNs; a conforming cart must not depend on
NaN payloads.** Everything else — integer arithmetic, `f32` rounding, linear
memory — is bit-identical across engines by the WASM spec itself, which makes
this binding *easier* to hold to golden frames than Lua was: the frame a cart
blits is the frame the suite diffs, on every host.

**This binding's goldens are RGB565 frames.** The palette-index goldens of §11
cannot represent a palette blit's 256 colours, so a wasm scene is judged on the
frame as shown, reduced to RGB565 — each channel's high bits, `r >> 3`, `g >> 2`,
`b >> 3`, row-major, little-endian. It is the finest form every host reproduces
exactly: a direct-colour host holds it and an RGB888 host reduces to it. Verbs
reduce through the cart's palette, a `blit` through the palette it was handed,
and a `blit565` frame is already in the golden's form.

## Distribution and AOT — host policy, not cart contract

How a host executes the `.wasm` is its own business, exactly as PSRAM placement
is (§1.1). The measured realities, recorded so ports plan for them:

- **Browser, desktop:** run the `.wasm` directly. No install step, and the
  browser is the fastest tier. This repository's web player instantiates the
  cart as a sibling module whose imports are adapters over the console's verbs —
  never a WASM interpreter nested inside a WASM console — and its desktop player
  runs the module on WAMR's interpreter, which a desktop has the speed for.
- **Reference RISC-V board:** external RAM carries no PMP entry, so a plain AOT
  module loads from a file straight into PSRAM and runs there, the caches synced
  after the loader writes the text — no flash partition, no per-install wear. The
  measured 16× *is* the slower XIP mode; plain AOT measured faster still
  (moybyte#158, 2026-09-24). XIP from a partition stays an option for a host that
  wants the text out of RAM.
- **Xtensa floor board:** loads the same way, from a file into PSRAM, through the
  chip's instruction-bus alias of external RAM. That alias is fetch-only, so the
  module is compiled without literal pools (`wamrc --size-level=0`). Doom runs on
  its glass from that path (moybyte#158).
- **Store fan-out:** a store may serve pre-compiled `.aot` variants per
  architecture alongside the canonical `.wasm`. `wamrc` ships prebuilt for x86-64 and RISC-V
  targets; the Xtensa backend is not in that binary and needs a build against
  Espressif's LLVM fork, which a store does once. Runtime and compiler versions
  must match (the evidence runs pin WAMR 2.4.5).

Integration frictions already catalogued by the evidence run, so the next
implementer inherits them: WAMR's `LIBC_WASI` defaults on and fails riscv32
builds; `REF_TYPES` defaults differ between its linux and esp-idf paths; a
`br_table`-heavy module loads on linux and is rejected by the esp-idf build
(dispatch through a function-pointer table instead); WAMR must run on a real
pthread under ESP-IDF; and its esp-idf platform layer needed fixes on both
boards (the S3's dual-bus mirror, executable PSRAM on the P4), which the
reference implementation carries in its pinned fork of WAMR.

## What Lua carts get from this: nothing, deliberately

There is no Lua→AOT path. The 16× comes from static types, not from WASM — the
1.09× interpreter is the control group — and honest Lua→C transpilation measures
in the 1.2–2× range elsewhere. A Lua cart that outgrows its budget is *ported*:
same verbs, same tick, same assets, and the twin-cart pattern the reference
implementation already uses (line-faithful Lua/Python pairs held bit-identical by
a parity harness) extends to a C twin checked by the same golden frames. A typed
Lua dialect (Pallene, Nelua) compiling into this pipeline is plausible and
unproposed.

An engine-shaped cart may embed its *own* interpreter — vendored Lua compiles to
wasm32 — running gameplay scripts inside a compiled engine. That needs nothing
from this spec.

## Open items

Decided items stay in the list, struck, with the date they closed, so the
numbering the issues cite keeps meaning.

1. ~~**Xtensa AOT on the floor board.**~~ **Measured 2026-09-24:** in scope, and it
   skips the install entirely — on both boards the module loads from a file into
   PSRAM. The floor board runs the same core at well under half the RISC-V
   board's rate, and Doom runs on its glass; numbers in moybyte#158.
2. **Measure `blit` through a console's frame loop**, not a bare harness. The
   import is built — libmoy's binding, run under WAMR on Linux by its own test —
   and what remains is the real full-frame cost inside a console's frame loop.
   `blit565` rides the same item: the two differ only in whether the host
   resolves a palette or copies.
3. **One integrated cart** — the flat-shaded raycaster in C is the natural twin,
   since its Lua sibling is already measured on glass.
4. ~~**A wasm twin of one conformance scene** passing an RGB565 golden
   (Determinism).~~ **Landed 2026-09-26:** `conformance/wasm_run.py` holds a
   scene per import only this binding has, the ordinary verbs through it, §11's
   `primitives` as a compiled cart, and a trap to RGB565 goldens, and refuses
   the shape fixtures, on three hosts of libmoy's binding: its WAMR harness, the
   desktop player and the web player, where the cart is a sibling module.
5. **`moy_cart.h`** committed here once the import list survives item 3.
6. **User-file access** (moybyte#108) is orthogonal to the cart-local `read`
   (item 10) and would be a separate import; it blocks the e-reader class of ports
   either way, and the WASI-subset question belongs to that issue, not this one.
7. ~~**The `blit565` penalty on the floor board.**~~ **Measured 2026-08-06**, and
   the prediction held with room to spare: the cart-side cost widened from
   +4.5–31 % to **1.1–3.3×**, and the host-side saving did not merely narrow, it
   went negative — the palette resolve is *cheaper* than the copy `blit565`
   would substitute for. Both boards' figures are in the section above. What
   remains open is only the bus speed: the floor-board run is at 80 MHz PSRAM
   because that board's flash is not verified for the high-performance mode
   `SPIRAM_SPEED_120M` needs. A 120 MHz rerun on verified flash would shrink the
   PSRAM-resident margins; it cannot reach the internal-SRAM rows or the
   allocation result.
8. **The figure for the compiled tier's memory floor.** §1.1's ≈400 KB is tier
   1's and stays there, and which number this tier uses is decided (Memory): the
   floor board's share of the cart-runtime reserve, measured with the runtime
   resident, against one integrated cart (item 3) rather than a derivation.
   `blit565`'s 153,600-byte framebuffer is most of why it has to move. What the
   floor bounds is the cart's whole footprint while it loads, not `"memory"`
   alone: the declared linear memory, the compiled module's code, and the
   engine's working pool are all resident at once, and on the reference
   console the code and pool of the first real port were over a megabyte of
   its load peak (moybyte#158). A check that bounds `"memory"` against the
   floor therefore has to leave that margin, and the figure lands in the
   Memory section and in `moy check`'s constant together, with the margin
   stated beside it. What the check does with the figure is decided: a cart
   above the floor draws a warning that names it, and the console that cannot
   fit the cart is the one that refuses it (Memory).
9. ~~**The `blit` palette is too small for the first real port.**~~ **Decided
   2026-09-25:** 256 entries, 768 bytes of RGB. Doom's palette is 256 entries and
   a frame uses well over 64 of them; the per-frame LUT stays noise at 256, and
   the alternative pushed every port onto `blit565`, which item 7 measured as the
   slow route on the floor board.
10. ~~**A ported engine needs to read its own assets.**~~ **Decided 2026-09-25:**
    `read`, read-only and scoped to the cart's own folder, pinned without waiting
    on the user-file question (item 6). The clock Doom also wanted is §9's
    `time()`, and there is no clock import.
11. ~~**PCM audio's shape**~~ **Decided 2026-09-29:** 22,050 Hz, mono, signed
    16-bit, and a queue of 2,048 frames, pinned by Doom, the first cart to need
    them; the PCM audio section says why. `snd` is in the import table, and a
    host with no audio drains its queue at the rate.
