# moy core — why each value

Companion to `SPEC.md`. Not normative. Every fixed number in the spec has an answer
here, so "why is it like that?" never gets met with "that's what we shipped."

Where an answer is **inherited** rather than reasoned, it says so. Those are the ones
most worth re-opening.

**One argument, one home.** This file owns the reasoning behind the spec's fixed
values; SPEC.md states each decision and its cost and points here. Three decisions run
the other way — `btnp` without autorepeat, no framebuffer access, and cover art as a
fixed-shape PNG — and are argued in SPEC.md §12.2, §12.6 and §12.7 because that is where they are
cited from; §12.1 records the one that was reversed, the screen palette. Either way there is one copy. When a
measurement changes, the doc that owns it is the only one to edit; `tools/check_docs.py`
is what notices when that stops being true.

---

## Raster — 320 × 240

Chosen because every implementation in the room already runs it, which makes it the
one number nobody has to be argued into. 4:3, and a clean 2× of 160 × 120 for hosts
that want to render small and upscale.

Cost of the choice: at one byte per index a framebuffer is 75 KB, which sets the
memory floor more than any other decision. A 240 × 160 raster would have halved it.

**Note for PICO-8 conversion:** 128 × 128 does not scale to fill 320 × 240 by an
integer factor — 2× is 256 × 256, taller than the screen. So a converted cart has
three ways out: run 1:1 centered in a letterbox; declare `"canvas": "128x128"`
(§3.1) and *be* a 128 × 128 machine, which the host then scales as it likes; or —
on top of the declared canvas — concede eight rows through the `viewport`
extension's guarded `view(128, 120)`, which lets a 4:3 host fill its height
(2× = 256 × 240, 5× = 640 × 600) while a host without the extension still
letterboxes the whole square.

The converter declares the canvas always and adds the `view` hint on request
(`--zoom`); nothing is cropped from the raster itself, so the cart draws native
p8 pixels everywhere and the loss — eight centered rows — happens only at
presentation, only on hosts that exploit the hint. (It once drew 2× itself into
a 320 × 240 canvas instead; that filled four times the pixels and baked one
host's geometry into every cart, and died when hosts learned to size the raster.)

## Canvas — three sizes, and the set is closed

320 × 240 is the console; 160 × 120 and 128 × 128 are the two smaller rasters a cart
may declare instead (§3.1). Each earns its place: 160 × 120 is a chunkier pixel, which
is a look a cart cannot fake by drawing bigger, and it is exactly half the default in
each axis, so a host already rendering small and upscaling (above) needs no new
scaler for it. 128 × 128 is in the set for one reason only — it is the shape of the
back catalogue this format wants to inherit.

Closed rather than arbitrary, because both of the properties that make this a
*console* survive only if the sizes are known in advance. A host provisions a
fixed-size machine (§1.1), and the smaller rasters are prefixes of the same
reservation, so the memory floor does not move. And a host can choose its scaler per
size ahead of time, where arbitrary dimensions would demand a general one from a
device that may only have a fixed-function scaler — or none.

An out-of-set value is **refused**, not clamped or ignored, for the same reason an
unknown `runtime` is (§3.1): a cart run at a size it did not ask for has every
coordinate in it wrong, and reports that as the author's bug.

## Tick — 30 Hz, 60 opt-in

30 is what the slowest conforming hardware sustains with a full-screen game and
headroom for hiccups. A steady 30 reads as smoother than a jittery 45, so the console
prefers a floor everyone can hold to a ceiling some can.

60 is opt-in per cart rather than per host because whether 60 is achievable is a
property of the *cart*, not the machine. Measured on reference hardware at this
raster, real games land between roughly 37 and 61 fps, which is precisely why 60
can't be the default and can't be forbidden either.

Drawing on an integer divisor of the tick (logic at full rate, draw every second
or third tick) is the only sanctioned degradation because it keeps game *time* real
— physics and input stay correct, only motion smoothness drops — and because an
integer divisor is the only even one: drawing three ticks in four delivers frames at
alternating intervals, which reads as judder rather than as a lower rate.

## Palette — 64 entries, cart-replaceable

64 is the size of the index space, not an aesthetic claim. It is the largest table
that keeps the index→native lookup trivially small (128 bytes as an RGB565 LUT, so it
lives in fast memory on any host) while leaving room past what 8 × 8 tile art uses.
The canvas is one byte per pixel regardless, so the count costs nothing at the
framebuffer.

The default table's *specific* colors: indices 0–15 are PICO-8's, byte-exact, so
converted carts keep their exact look. 16–63 were originally chosen for a desktop
shell's needs — wallpaper and UI, pastels and earth tones — and are **inherited**.
Cart-supplied palettes make this mostly moot: the default is a starting point, not a
constraint.

## Sprites — 16 colors

**Format compatibility, not memory.** One hex nibble per pixel is exactly PICO-8's
`__gfx__` sheet, which is what makes the converter nearly free. The constraint is
sixteen *at a time*, not sixteen specific colors, since the cart picks the table.

## Sheet — 512 tiles, 128 × 256

254 is the map's addressing ceiling, and level geometry rarely needs more distinct
tiles than that. But sprite and animation art does. So the sheet doubles past the
map's reach and the extra space goes where the pressure is.

512 rather than 1024: 1024 tiles is 64 KB and 65,536 pixels of unique art for a screen
that holds 76,800 — more distinct art than small games fill, and a sheet editor paging
1024 tiles on a small screen is unpleasant to use.

The sheet grows **down** (sixteen tiles per row, twice the rows) rather than sideways,
because sideways renumbers every tile — id `n` moves to `(n // 16) * 32 + (n % 16)` —
invalidating every existing sheet, every map and the whole converted PICO-8 catalogue
in exchange for nothing. Downward, a 128-line sheet is simply the top half and every
id keeps its pixels. Wider would have made multi-tile sprite neighbourhoods marginally
more convenient; id stability is worth more.

**Inherited from PICO-8 and then revised:** 256 was the original value, copied from a
console with a 128 × 128 screen. At 320 × 240 that is six times the pixel area on the
same tile vocabulary, which is why it moved.

## Tilemap — one byte per cell, `tile_id + 1`

Storing `id + 1` means `00` is empty and a zeroed map is genuinely blank — no sentinel
value, no separate occupancy mask, and a blank map compresses to nothing. The cost is
a 254-tile ceiling.

Two bytes per cell would lift the ceiling to 65,534 but doubles map memory and takes
the hex format to four characters per cell, hurting the readability that made a text
format worth choosing. Not worth it for level geometry.

## Buttons — 4 directions plus A and B, host-mapped

Six is PICO-8's set, and that constraint is a large part of why its games port
anywhere. It is also the largest set every known implementation can produce: one
device has no d-pad, another has no touchscreen, so the console defines *logical*
buttons and each host maps its own hardware.

`run` is optional because not every device has a third comfortable button.

Exit is not in the set at all: it belongs to the host, so no cart has to spend a
button on it and no host has to honour a cart's idea of quitting. `quit()` (§9) is the
complement rather than a contradiction — the *player* leaves without the cart's
cooperation, the *cart* ends itself — and the two only overlap in `textmode`, where
the host's own gesture cannot reach through a stream of typed characters.

**Touch and keyboard are optional but never required** because a cart requiring
hardware half the devices lack fragments the catalogue on day one. That is the single
rule most likely to be quietly broken, so it is stated as a conformance requirement
rather than advice.

## Players — core, not an extension

Local multiple controllers degrade cleanly: a cart asks `players()`, gets 1 on a
single-pad console, and offers versus mode or doesn't. A capability that degrades
cleanly should never be something a cart declares, because declaring it means being
*refused* by every console that lacks it — a strictly worse outcome than running in
single-player.

Networking is the opposite and is therefore not here at all. It cannot degrade: a cart
built around a low-latency mesh does not become a working cart on a browser socket, it
becomes a broken one. Extensions are for capabilities whose absence a cart cannot
paper over.

## Sandbox — base, math, string, table, coroutine

The smallest set that supports ordinary game code. Everything excluded (`io`, `os`,
`debug`, `package`) either reaches the host system or lets a cart load code the
sandbox never inspected.

Stated as a **maximum** because the failure mode is asymmetric: a host that exposes
less breaks some carts loudly, while a host that exposes more silently accumulates
carts that run nowhere else. Only the second kind of divergence kills a format.

`coroutine` was the one omission that failed that test — it is pure computation,
and cutscene and animation code in both source consoles is written with it, so a
state-machine rewrite was the tax every port paid. It is in. The excluded set is
exactly the libraries that reach outside the VM.

## Numbers — 32-bit

Integers wrap at ±2.1 billion, floats carry ~7 digits. This puts float math on the
hardware FPU of typical target silicon and halves the size of every value in the VM,
which matters for cache behaviour on small hardware. What games at this scale actually
count — scores, timers, positions — does not need more.

## Memory — 400 KB

Sum of the fixed allocations plus headroom: 75 framebuffer + 32 sheet + 16 map + 192
cart heap + 8 audio. The cart heap is the one soft number, sized from a measured
41 KB footprint for a fully-bridged reference cart, so it is roughly 4× observed need.

**Not yet profiled against a running console** — it is derived, not measured. It is
also the number most likely to be wrong in the direction of too generous.

**PSRAM counts.** The floor is capacity the verbs can run against, not a demand for
internal SRAM — the reference boards keep the framebuffer and assets in external
PSRAM and steer only the Lua VM's hot allocations to SRAM (an all-PSRAM heap
measured roughly 2× slower cart logic on one board's 120 MHz octal bus — a quality
trade, invisible to carts). So the number only bites SRAM-only parts, which is
exactly the boundary it is meant to draw: on anything with external RAM the real
constraint is memory *bandwidth*, and that shows up as frame rate, not conformance.

## Audio — 4 channels, PICO-8-parity fidelity

Music claims channels from the top and effects round-robin the rest, so a sound
effect can never cut the background loop. Four voices of waveform synthesis is a
small enough mixing load to run on the CPU of any target (the reference ESP32
implementation mixes all four with effects for ~1–2% of one core), and matches
what 8-bit-era music actually used.

The model deliberately covers PICO-8's: 8 waveforms, a per-note effect column in
PICO-8's own numbering, and multi-channel music rows. The catalogue story leans
on ports, and a port whose music lost three of four channels and every slide is
audibly wrong — so p8 is the *floor* of fidelity, not an aspiration. Effect
semantics are specified musically (what a slide does), not sample-exactly.

Pitch as a semitone index (0–95, C0–B7, 57 = A4 = 440 Hz) rather than raw Hz because
it is what a note editor wants and what a person writing a melody thinks in.

Volume 0–7 is **inherited** from the reference implementation's audio model;
nothing depends on the specific range.

Audio is excluded from pixel conformance because two synths will not produce identical
samples, and requiring that would fail every implementation for no benefit.

## Save data — 256 integers

TIC-80's `pmem` size, which is also what the reference implementation has always
shipped. At 32 bits a slot that is 1 KB per cart — against the §1.1 floor of roughly
400 KB, three quarters of a kilobyte sits inside the headroom and changes no
conformance decision. The SRAM-only parts §12.4 rules out are ruled out by the
framebuffer and the cart heap, not by this.

**Inherited, and corrected once.** An earlier draft said 64 — PICO-8's `cartdata`
size — which left the spec holding TIC-80's *name* for the verb and PICO-8's *number*
for its size. Two arguments settled it. The failure modes are lopsided: a cart written
against 256 slots and run on a 64-slot host does not fail loudly, it drops the writes
and reads back zeros, so the player simply finds their progress gone. The other
direction costs 768 bytes. And only one direction can break something that already
exists — every cart written against 64 slots runs unchanged on a 256-slot host, never
the reverse.

The boundary the smaller number was defending is still real: a cart wanting more than
this is probably wanting a filesystem, which §0 puts out of scope on purpose. It just
does not sit at 64. What runs past it is the ordinary case, a flag or a star count per
level, not a cart smuggling in a save format.

## `spr_batch` — why it *left* core

It was core in an earlier draft as a **dispatch** feature rather than a drawing one:
on an interpreted host the language boundary dominates small draws, so one call doing
N sprites looked like it earned a verb.

Checked against the reference console, it didn't. That console's Lua `spr` appends each
quad straight into the native batch array and breaks the run only on a state change or
a full queue — so an ordinary `for` loop of `spr` calls never crosses the boundary at
all, and already compiles to the one batched call `spr_batch` would have made. Two
things made it dead weight rather than merely redundant: no cart in the spec's own
language ever called it, and its binding was broken, which is how nobody noticed.

`rect_batch`, `col_batch` and `spans` followed it out on their own measurements (§6.1
records those). Hence the rule §6.1 now states as a host's duty: a batching win the
engine can find for itself is the engine's job, and a cart is never asked to pre-pack
its geometry.

## `config.json`

The cart's own tuning surface: values a person can change without touching code —
difficulty, counts, colors, developer and debug switches. Costs a host nothing (read a
flat JSON map, hand values to `cfg`) and gives any host that wants one somewhere to
hang a settings UI.

---

## The §6.1 verbs — answered, and the measurement that changed the answer

The set is `tri`, `trib`, `sspr` and `tline`, and §6.1 states the rule that admits
them. What matters here is that turning many calls into one never qualified.

That rule is the *result* of a correction, and the correction is this document's own,
which is why it is recorded here rather than there. An earlier draft of this file
argued the opposite case from a measurement that was wrong: that tall narrow spans cost
~4× per pixel what wide ones do, so the cost was memory order rather than dispatch, so
a column-shaped verb should recover it. **That figure was a subtraction artifact**, the
real gap is far smaller, and the verb built on it measured *slower* than the one it was
meant to replace. So `spr_batch`, `rect_batch`, `col_batch` and `spans` are deleted and
batching is the host's duty.

The numbers that settled all of it — the corrected per-pixel costs, `col_batch`'s A/B,
and the per-technique frame budgets on the reference boards — are tabulated in
SPEC.md §6.1 and are not repeated here. That section is where an implementer looks
before re-proposing one of them, and a measurement quoted in two places is a
measurement that will be retracted in one.

The lesson, which is general: a confident write-up outlives the code it measured, and
nobody re-runs a number that reads like a verdict.

---

## The WebAssembly binding

SPEC.md §15 says why a second binding exists and §16 is the contract; this is the
evidence under it. The first run is a 6502 interpreter core, line-faithful in Lua and
C with identical cycle counts out of every runtime, on the reference console's RISC-V
board at its shipping clock (moybyte#158, 2026-07-27), and the same core on the
Xtensa floor board since 2026-09-24.

### Why AOT, and why not an interpreter

| runtime | 6502 instr/s | vs Lua | arithmetic (`spin`) |
|---|---|---|---|
| Lua (the shipping binding) | 0.173 M | 1.0× | 5.2 M ops/s |
| WASM, WAMR fast-interp | 0.188 M | **1.09×** | 12.35 M |
| WASM, AOT (XIP — the *pessimistic* mode) | 2.828 M | **16.3×** | 476 M (**91×**) |

Two conclusions, both load-bearing: **interpreted WASM does not justify a runtime** —
its advantage collapses exactly on dispatch-shaped code, which is what interpreters
and emulators are — and **AOT does**. An interp-only evaluation would have said no and
been wrong. How a host executes a module stays its own business all the same
(PORTING.md): the numbers argue for the binding, not for one execution strategy.

### Why nothing for Lua carts

The speed comes from static types, not from WebAssembly: the interpreter row above
is the control group, and honest Lua-to-C transpilation measures in the 1.2–2× range
elsewhere. So there is no Lua-to-AOT path; a slow Lua cart gets ported instead,
and the twin-cart pattern the reference implementation already uses
(line-faithful pairs held bit-identical by a parity harness) extends to a C twin
checked by the same golden frames. A typed Lua dialect (Pallene, Nelua) compiling
into this pipeline is plausible and unproposed. An engine-shaped cart may embed its
own interpreter — Lua compiles to wasm32 — to run gameplay scripts inside a compiled
engine, and that needs nothing from the spec.

### `blit` — why a whole frame, and why 256 entries

Measured budget: about 4.6 M pixel-writes/s from AOT code into linear memory against
476 M ops/s of arithmetic, so a full-screen software raster lands around 17 ms on the
measured board, inside a 30 fps frame with the geometry effectively free. The
boundary, not the speed, was the blocker, which is why the import hands over a frame.

The palette is 256 entries because the first real port needed it: Doom's palette is
256 entries and a frame uses well over 64 of them (decided 2026-09-25). With 256 any
game holding 256 or fewer simultaneous colours maps exactly, fades included, and the
per-frame table stays noise to rebuild; the alternative pushed every port onto
`blit565`, which the next section measures as the slow route on the floor board. The
NES needs none of this — its 54-entry master palette is fixed hardware and fits §2.2
as it is — and neither do the GB's 4 shades.

### `blit565` — why it is not the default

Measured on an ESP32-P4 (360 MHz, PSRAM 200 MHz, 256 KB L2, `-O2`), one rasterizer
compiled twice from a single source, differing only in stored pixel type:

| the cart's own raster | 8-bit indices | RGB565 |
|---|---|---|
| filled rects | 988 µs | 1292 µs (**+31%**) |
| textured scanlines | 6780 µs | 7455 µs (+10%) |
| scaled sprite columns | 7921 µs | 8518 µs (+7.5%) |
| triangles | 4789 µs | 5004 µs (+4.5%) |

Against the ~17 ms full-screen budget above, choosing `blit565` costs the cart
**+0.8 to +5.3 ms**, and it saves the host only ~0.8 ms: the difference between
resolving a palette (1148 µs with a pixel-pair table; 2026 µs with a per-pixel loop)
and copying 153,600 bytes (344 µs). Best case a wash, worst case six times worse. More
optimization does not close the gap either: every lookup's address depends on the
byte just loaded, so the resolve plateaus around 3× a copy, where a copy has no
dependency chain at all.

**On the floor board it is not close.** The same bench on an ESP32-S3 at 240 MHz with
octal PSRAM and no L2 — the board a cart is most likely to be too slow on, and
therefore the one that decides (measured 2026-08-06):

| the cart's own raster | 8-bit indices | RGB565 |
|---|---|---|
| filled rects | 3226 µs | 10615 µs (**3.3×**) |
| triangles | 9410 µs | 21853 µs (**2.3×**) |
| scaled sprite columns | 18466 µs | 25163 µs (1.4×) |
| textured scanlines | 18275 µs | 20823 µs (1.1×) |

A 32-bit fill store covers four indexed pixels and only two RGB565 ones, and with no
cache to absorb it the wider format is paid in full. The host side inverts too: with
the source half the size, the palette resolve is **cheaper than the copy it would
replace** — 1681 µs against 2483 µs into the panel's bounce buffer. So on this board
`blit565` costs the cart up to 3.3× and saves the host nothing. That is why SPEC.md
§16.5 keeps a cart indexed whenever its pixels allow: advice on the faster board, close to a requirement on the floor board, and a cart is judged on the
floor board.

The floor-board figures are at 80 MHz PSRAM, not the 120 MHz the reference console
ships: that board's flash is not verified for the high-performance mode
`SPIRAM_SPEED_120M` requires, and a 120 MHz build aborts in MSPI timing init. 80 MHz
makes external memory dearer than it really is, so the margins are generous — but the
3.3× is far outside what a bus-speed correction reaches, and the internal-SRAM rows do
not depend on it at all.

It is also why the binding declares its own memory floor (SPEC.md §16.7). 153,600
bytes against §1.1's 192 KB cart heap leaves about 40 KB for the game, and on the
floor board, with the console's own 76,800-byte canvas resident, a second
153,600-byte buffer could not be allocated contiguously in internal SRAM at all — on
an otherwise empty heap. A `blit565` cart there is committed to external memory for
its framebuffer, which is exactly where the 3.3× comes from.

### `snd` — why 22,050 Hz and 2,048 frames

22,050 Hz is the rate the reference console's boards output and PICO-8's own, so on
the hardware tier a stream reaches the speaker unconverted and costs the console one
add per sample. Doom's effects are 11,025 Hz, an exact half. The boards' speakers
carry nothing a higher rate would add, and 44,100 Hz doubles the cart's mixing and the
copy for none of it. Mono because every speaker in the reference lineup is one
speaker and §8.3 mixes to mono; a cart with stereo sources folds them itself.

The first cart to use the stream, Doom, draws in the 30s and 40s of fps on the floor
board — 25 to 35 ms a frame, and a WAD read over SD adds 5 (moybyte#158). 2,048 frames
is more than two frames at 30 fps before the stream runs dry; half that is under two,
one hitch from a gap, and twice that puts a sound effect a sixth of a second behind
the frame that caused it (decided 2026-09-29).

### `par` — why fork-join, not threads

Threads — shared memory, atomics and a spawn, as wasi-threads has them — would let a
cart build any synchronisation it liked, and would cost the binding its determinism
and its portability: the memory would have to be declared shared, which a browser
gives only a cross-origin-isolated page; a cart could race, or spin on another core
for ever; and on the Xtensa floor board, whose linear memory is in external RAM, the
CPU's compare-and-swap does not work there, so every atomic becomes a lock. The work
that wants the cores does not need them either. Jet's own ESP32 runtime draws with two
cores by keeping the frame's setup on one and cutting the frame's rows into bands that
rasterize at once, then joining — fork-join exactly, with the memory unshared. A
single-core host needs nothing but a loop (decided 2026-09-29; what it measures is
moybyte#158's).

The reference console gives a cart every core but the one its session runs on, below
the display and audio tasks' priority, and each core takes the next item as it
finishes one, so a busier core takes fewer.
