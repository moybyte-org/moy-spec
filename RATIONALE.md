# moy core — why each value

Companion to `SPEC.md`. Not normative. Every fixed number in the spec has an answer
here, so "why is it like that?" never gets met with "that's what we shipped."

Where an answer is **inherited** rather than reasoned, it says so. Those are the ones
most worth re-opening.

---

## Raster — 320 × 240

Chosen because every implementation in the room already runs it, which makes it the
one number nobody has to be argued into. 4:3, and a clean 2× of 160 × 120 for hosts
that want to render small and upscale.

Cost of the choice: at one byte per index a framebuffer is 75 KB, which sets the
memory floor more than any other decision. A 240 × 160 raster would have halved it.

**Note for PICO-8 conversion:** 128 × 128 does not scale to fill 320 × 240 by an
integer factor — 2× is 256 × 256, taller than the screen. Converted carts run 1:1
centered, or use the `view` extension to letterbox at the host's best fit.

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

## Sheet — 512 tiles, 256 × 128

254 is the map's addressing ceiling, and level geometry rarely needs more distinct
tiles than that. But sprite and animation art does. So the sheet doubles past the
map's reach and the extra space goes where the pressure is.

512 rather than 1024: 1024 tiles is 64 KB and 65,536 pixels of unique art for a screen
that holds 76,800 — more distinct art than small games fill, and a sheet editor paging
1024 tiles on a small screen is unpleasant to use.

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
button on it and no host has to honour a cart's idea of quitting.

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
which matters for cache behaviour on small hardware. Kid-scale games — scores, timers,
positions — do not need more.

## Memory — 400 KB

Sum of the fixed allocations plus headroom: 75 framebuffer + 32 sheet + 16 map + 192
cart heap + 8 audio. The cart heap is the one soft number, sized from a measured
41 KB footprint for a fully-bridged reference cart, so it is roughly 4× observed need.

**Not yet profiled against a running console** — it is derived, not measured. It is
also the number most likely to be wrong in the direction of too generous.

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

## Save data — 64 integers

PICO-8's `cartdata` size, and enough for high scores, progress flags and unlocks —
the things a small game persists. A cart wanting more is probably wanting a filesystem,
which §0 puts out of scope on purpose.

## `spr_batch`

Not a drawing feature — a **dispatch** one. On an interpreted host, crossing the
language boundary dominates small draws, so one call doing N sprites is worth a
dedicated verb. Semantically identical to a loop; a compiled host may implement it as
exactly that and lose nothing.

## `config.json`

The cart's own tuning surface: values a person can change without touching code —
difficulty, counts, colors, developer and debug switches. Costs a host nothing (read a
flat JSON map, hand values to `cfg`) and gives any host that wants one somewhere to
hang a settings UI.

---

## The §6.1 verbs — deliberately unanswered

`rect_batch`, `col_batch`, `tri`/`trib` and `sspr` have no entry here yet, because
their numbers are still being measured. The one thing already established is the
observation that motivates them: on reference hardware, tall narrow spans cost ~4× per
pixel what wide ones do (~300ns/px vs ~74ns/px), and that gap persists when the same
work moves from a script into a C kernel — so it is memory order, not dispatch.

Everything that follows from that (whether a column-shaped verb recovers it, whether
the right level is a primitive or a whole renderer) is open. See SPEC.md §6.1.
