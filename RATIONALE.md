# moy core — why each value

Companion to `SPEC.md`. Not normative. Every fixed number in the spec has an answer
here, so "why is it like that?" never gets met with "that's what we shipped."

Where an answer is **inherited** rather than reasoned, it says so. Those are the ones
most worth re-opening.

**One argument, one home.** This file owns the reasoning behind the spec's fixed
values; SPEC.md states each decision and its cost and points here. Four decisions run
the other way — no display-time palette, `btnp` without autorepeat, no framebuffer
access, and deferred cover art — and are argued in SPEC.md §12.1, §12.2, §12.6 and
§12.7 because that is where they are cited from. Either way there is one copy. When a
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

Frameskip (logic at full rate, draw every second tick) is the only sanctioned
degradation because it keeps game *time* real — physics and input stay correct, only
motion smoothness drops.

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

## Sandbox — base, math, string, table

The smallest set that supports ordinary game code. Everything excluded (`io`, `os`,
`debug`, `package`, `coroutine`) either reaches the host system or lets a cart load
code the sandbox never inspected.

Stated as a **maximum** because the failure mode is asymmetric: a host that exposes
less breaks some carts loudly, while a host that exposes more silently accumulates
carts that run nowhere else. Only the second kind of divergence kills a format.

`coroutine` is the most defensible omission to revisit — it is pure computation and
some game structures want it.

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
and the per-technique frame budgets on both reference boards — are tabulated in
SPEC.md §6.1 and are not repeated here. That section is where an implementer looks
before re-proposing one of them, and a measurement quoted in two places is a
measurement that will be retracted in one.

The lesson, which is general: a confident write-up outlives the code it measured, and
nobody re-runs a number that reads like a verdict.
