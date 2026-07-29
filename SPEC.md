# moy core 0.1 — the portable console spec

> **Status: DRAFT 0.1.** Everything outside §6.1 is decided and implemented — it
> describes a console that exists and runs games today, not a design sketch.
> **§6.1 (batched fills and the 3D verbs) is explicitly TBD** and is not part of 0.1.
> Decisions worth arguing about are collected in §12 with their reasoning.

**moy** is a virtual console: a fixed raster, a fixed palette, a fixed set of
drawing, input and audio verbs, and a cart format that packages a game against them.
A *cart* is a folder you hand the console; it plays.

Any device that implements this spec runs any cart. That is the entire point. The
console deliberately says nothing about CPU, OS, windowing, filesystems, or app
lifecycle — those belong to whatever system hosts it.

### core, and what sits above it

This document defines **moy core**: the part every implementation provides, and
therefore the part a cart can rely on running anywhere. It is deliberately small.

Consoles will do more than core. That is expected and fine — a console with a
scripting extension, a document format, a radio, a second cart language, or a
windowing shell loses nothing by having them. Those are **extensions** (§10): a cart
that needs one declares it, and a host that lacks it refuses the cart cleanly instead
of failing halfway through a frame.

The one rule: **an extension must not redefine anything core already covers.** Add
verbs, add asset kinds, add capabilities — but where an implementation and core
disagree about something core specifies, the implementation is what changes. Core is
a subset of every conforming console, never a dialect of one.

---

## 0. Scope

**In scope:** the raster, the palette, the verb table and its exact semantics, the
tick model, the sandbox ceiling, the audio model, the cart package layout.

**Out of scope, permanently:** windows, OS calls, drivers, networking beyond the
optional extension in §10, filesystem access, app install/lifecycle, anything a cart
could use to reach the host system. A cart draws, reads input, plays sound, and saves
a little state. That constraint is what makes the same cart run on a handheld, a
desktop simulator, and someone else's OS.

---

## 1. The console

| property | value |
|---|---|
| Screen | **320 × 240**, palette-indexed |
| Palette | **64 entries** (§2), indices 0–63, cart-replaceable |
| Sprite sheet | **512 tiles** of 8 × 8, drawn from palette indices **0–15** |
| Tilemap | one grid, cells hold a tile id 0–254 |
| Audio | **4 channels**, 8 waveforms, per-note effects (§8) |
| Tick | **30 Hz** guaranteed; 60 Hz opt-in (§5) |
| Language | **Lua 5.4**, sandboxed (§4) |
| Origin | top-left, `+x` right, `+y` down |

A host whose physical display is not 320 × 240 scales and/or letterboxes the console
raster onto its glass. The cart never learns the physical resolution. Integer scaling
is recommended; the choice is the host's.

### 1.1 Memory the host must provide

The console is a fixed-size machine. A conforming host reserves this for it, however
it likes — statically, from a pool, or by shutting down other subsystems while a cart
runs:

| allocation | size | note |
|---|---|---|
| Framebuffer | **75 KB** | 320 × 240 at one byte per index. A host rendering direct to RGB565 pays 150 KB instead — its choice, not the cart's |
| Sprite sheet | **32 KB** | 128 × 256 pixels, one byte per pixel in RAM |
| Tilemap | **16 KB** | one byte per cell, up to 128 × 128 cells |
| Cart heap | **192 KB** | the Lua VM and everything the cart allocates |
| Audio | **8 KB** | bank plus mix buffer |
| | | |
| **Core total** | **≈ 400 KB** | with headroom |
| **With `layers`** (§10) | **≈ 1 MB** | each full-screen off-screen buffer is another 75 KB |

For calibration: a measured fully-bridged cart on the reference implementation uses
about 41 KB of Lua heap, so 192 KB is generous rather than tight.

**This is a floor, not a target.** A host that cannot free 400 KB while a cart runs
cannot conform — freeing it is the implementer's problem, and a "game mode" that
suspends other subsystems for the duration is a perfectly good way to solve it.

**The kind of RAM is not specified.** Internal SRAM, external PSRAM, or any mix
qualifies — if `_update` and the drawing verbs hold the tick rate against it, it
counts. That makes the floor trivial on PSRAM-equipped boards (most ESP32-class
devices carry megabytes) and binding only for single-die parts: 400 KB deliberately
excludes the smallest SRAM-only microcontrollers (§12.4). Placement is a quality
concern, not a conformance one — the reference implementation keeps its framebuffer
and assets in PSRAM and steers only the Lua VM's hot allocations to internal SRAM,
after measuring an all-PSRAM heap at roughly 2× slower cart logic on one board's
120 MHz octal bus. A cart can observe none of this.

---

## 2. Palette

64 RGB888 entries. Indices **0–15 are the PICO-8 base palette**, unchanged and
byte-exact, so converted PICO-8 carts keep their exact colors:

| idx | name | RGB | idx | name | RGB |
|---|---|---|---|---|---|
| 0 | black | `000000` | 8 | red | `FF004D` |
| 1 | dark_blue | `1D2B53` | 9 | orange | `FFA300` |
| 2 | dark_purple | `7E2553` | 10 | yellow | `FFEC27` |
| 3 | dark_green | `008751` | 11 | green | `00E436` |
| 4 | brown | `AB5236` | 12 | blue | `29ADFF` |
| 5 | dark_grey | `5F574F` | 13 | indigo | `83769C` |
| 6 | light_grey | `C2C3C7` | 14 | pink | `FF77A8` |
| 7 | white | `FFF1E8` | 15 | peach | `FFCCAA` |

Indices 16–63 extend the base with pastels, earth tones, vivid accents, neutrals and
deep shades. The full default table ships as `palette.json` beside this spec —
conformance needs exact values, so it is data, not prose.

### 2.1 Why 64

64 is the size of the **index space**, not a claim about how many colors art needs.
It is the largest table that keeps the index→native-pixel lookup trivially small —
128 bytes as an RGB565 LUT, so it fits in fast memory on any host — while leaving
room well past what 8 × 8 tile art uses. The canvas stores one byte per pixel either
way, so the choice costs nothing at the framebuffer.

The *colors* are not fixed by this spec — see below.

### 2.2 Cart-supplied palettes

A cart MAY ship its own table by including a `"palette"` array in its manifest: 64
RGB hex strings, index order.

```json
"palette": ["000000", "1D2B53", "7E2553", "..."]
```

Absent, the default table applies. Present, it replaces the default entirely for that
cart's lifetime. It costs 192 bytes and it means the default palette is a convenience,
not a constraint — a converted PICO-8 cart simply ships PICO-8's sixteen, and an
artist who wants a specific mood ships that.

`pal()` remaps index to index and is unaffected by which table is loaded.

### 2.3 Sprites use indices 0–15

Primitives (`cls`, `rect`, `line`, `circ`, `print`) may use the full 0–63; sprite
pixels may not.

This is not a memory compromise, it is **format compatibility**: one hex nibble per
pixel is exactly PICO-8's `__gfx__` sheet format (§3.2), which is what makes
converting existing carts nearly free. Sixteen-color sprites are what buy the back
catalogue. With cart-supplied palettes, *which* sixteen is up to the cart.

Hosts resolve indices to their native pixel format at flush time. The canvas itself is
always indices.

---

## 3. Cart format

A cart is a **folder**:

```
mygame.moy/
  manifest.json      required
  main.lua           required
  sprites.moygfx     optional — the sprite sheet
  map.moymap         optional — the tilemap
  sounds.json        optional — the audio bank
  config.json        optional — author-exposed tuning values
```

That folder is the whole format. How the folder *travels* — a zip, a tarball, a
git clone, a directory on an SD card — is packaging, and this spec says nothing
about it for the same reason it says nothing about filesystems (§0). A host that
wants to accept an archive unpacks it and hands the console a folder.

### 3.1 manifest.json

```json
{
  "format": "moy-1",
  "title": "Star Catcher",
  "author": "kenny",
  "version": 1,
  "main": "main.lua",
  "fps": 30,
  "input": ["buttons"],
  "extensions": []
}
```

| field | required | meaning |
|---|---|---|
| `format` | yes | `"moy-1"` |
| `title` | yes | display name |
| `author` | no | |
| `version` | no | integer, author's own versioning |
| `main` | no | entry script, default `main.lua` |
| `fps` | no | `30` (default) or `60` — see §5 |
| `input` | no | input groups the cart reads — see §7.3 |
| `palette` | no | 64 RGB hex strings replacing the default table — see §2.2 |
| `extensions` | no | optional features required — see §10 |

A host MUST ignore manifest fields it does not recognise. Implementations hang
vendor metadata there (the reference console records editor state in fields of its
own), and future minor versions may add fields — neither may break an existing host.

One such field is worth naming because the converter writes it: **`"ported_from"`**,
a short string identifying the cart's source format (`"pico-8"`). Purely
informational — a host may show it, and ignoring it costs nothing.

### 3.2 sprites.moygfx

PICO-8 `__gfx__` format, extended *downward*: one hex nibble per pixel, **128
characters per line, up to 256 lines**, forming a 128 × 256 pixel sheet. Tiles are
8 × 8, addressed row-major, sixteen per row — tile `n` has its top-left at
`((n % 16) * 8, (n // 16) * 8)`. **512 tiles.** A file with fewer than 256 lines
leaves the remaining tiles blank (all zeros); hosts MUST accept short sheets.

Human-readable, diff-able, and character-for-character the format PICO-8 emits — a
128 × 128 PICO-8 sheet **is** the top half of a moy sheet, tile ids unchanged. The
sheet grows down rather than sideways precisely so ids never remap: existing art
and converted carts stay valid as the space doubles.

Tiles **0–254** can be placed on the tilemap (§3.3); the full **0–511** range is
available to `spr()`. The split is deliberate: level geometry rarely needs more than
254 distinct tiles, and holding map cells to one byte keeps maps small and readable,
so the extra sheet space goes where the pressure actually is — sprite and animation
art.

### 3.3 map.moymap

A header line `w h`, then `h` rows of `w * 2` hex digits — one byte per cell,
big-endian pair, mirroring the sheet's format.

Each byte stores **`tile_id + 1`**, so `00` is an empty cell and an all-zero map is
genuinely blank. Tile ids therefore run **0–254**; sheet tile 255 cannot be placed on
a map.

`w` and `h` are each at most **128**, so the largest map is 128 × 128 cells =
16 KB — the allocation §1.1 requires a host to reserve. A host MUST reject a map
declaring larger dimensions rather than allocating past its budget. (For scale:
PICO-8's map is 128 × 64, so a converted cart fits with room.)

```
15 15
000000000000000000000000000000
000a0a0009090000000909000a0a00
...
```

---

## 4. Program model

A cart is one Lua 5.4 script. It defines up to three global functions and calls the
console verbs, which are pre-injected as globals. **No `require`, no imports.**

```lua
local x, y = 0, 0

function _init()                     -- once at start
  x, y = W // 2, H // 2
end

function _update(dt)                 -- every tick, before draw
  local speed = 120 * dt
  if btn("left")  then x = x - speed end
  if btn("right") then x = x + speed end
end

function _draw()                     -- every rendered frame
  cls(1)
  circ(flr(x), flr(y), 6, 10)
  print("MOVE ME", 8, 8, 7)
end
```

All three hooks are optional. `dt` is **seconds since the last update**, a float.

### 4.1 Sandbox

The available Lua standard library is exactly:

**`base`** (minus `load`, `loadstring`, `dofile`, `require`, `collectgarbage`),
**`math`**, **`string`**, **`table`**.

Absent entirely: `io`, `os`, `debug`, `package`, `coroutine`.

This is a **maximum, not a suggestion.** A host that exposes more accumulates carts
that run nowhere else, which breaks the format for everyone. Conformance tests it.

### 4.2 Numbers

Lua is built with **`LUA_32BITS`**: integers are 32-bit and wrap at ±2,147,483,647;
floats are 32-bit and carry about 7 significant digits. This puts float math on the
hardware FPU of typical target silicon and halves the size of every value in the VM.

A cart must not depend on more precision than that. A host built with 64-bit doubles
still conforms — it is strictly more precise — but it may drift from the golden
frames on float-heavy carts, since those are captured from a 32-bit build (§11).

### 4.3 Errors

A Lua error terminates the cart. The host reports it to the user with the script line
number and returns to wherever the cart was launched from. A host MUST NOT leave a
crashed cart running or silently swallow the error.

---

## 5. Tick

The console ticks at **30 Hz**. A cart may declare `"fps": 60`; hosts that cannot
sustain 60 for that cart fall back to 30 rather than running at an unstable rate in
between.

`_update(dt)` and `_draw()` are each called once per tick, in that order.

A host under load MAY skip `_draw()` on alternating ticks while continuing to call
`_update(dt)` at the full rate — logic stays real-time, motion halves. This is the
only sanctioned form of degradation.

`dt` always reflects real elapsed time, so movement written as `speed * dt` is correct
at any rate.

---

## 6. Drawing

All coordinates are canvas pixels, all colors palette indices. Every verb clips to the
canvas and honours the current `camera`, `clip` and `pal` state.

| verb | effect |
|---|---|
| `cls(c)` | clear the screen to color `c` (default 0) |
| `pix(x, y, c)` | set one pixel |
| `line(x0, y0, x1, y1, c)` | line |
| `rect(x, y, w, h, c)` | **filled** rectangle |
| `rectb(x, y, w, h, c)` | rectangle **outline** |
| `circ(cx, cy, r, c)` | **filled** circle |
| `circb(cx, cy, r, c)` | circle **outline** |
| `tri(x1, y1, x2, y2, x3, y3, c)` | **filled** triangle — ⚑ TBD, see §6.1 |
| `trib(x1, y1, x2, y2, x3, y3, c)` | triangle **outline** — ⚑ TBD, see §6.1 |
| `print(s, x, y, c)` | text, 8 × 8 fixed font |
| `camera(x, y)` | offset subsequent draws by `-x, -y`. No args resets |
| `clip(x, y, w, h)` | clip subsequent draws to a rect. No args resets |
| `pal(c0, c1)` | draw color `c0` as `c1`. No args resets |
| `palt(c, on)` | mark index `c` transparent. No args resets |

`pal` is **draw-time only** — it remaps colors as they are written to the canvas.
There is no display-time palette (§12.1).

`print` has no scale parameter; text is always 8px. The 8 × 8 font must be
byte-identical across implementations or all text conformance fails — it ships as
`font.bin` beside this spec: 96 glyphs covering ASCII `0x20`–`0x7F`, 8 bytes per
glyph, one byte per **column** left to right, LSB = top row. Codepoints outside
that range draw nothing and advance 8px like any glyph.

`font.bin` is MicroPython's `font_petme128_8x8`, MIT-licensed — shipping the
glyph data means shipping that notice. See `THIRD_PARTY.md`.

### 6.1 Batched fills and the 3D verbs — ⚑ TBD

> **This subsection is unsettled and is NOT part of 0.1.** Names, signatures and
> membership are all still moving, and one of the verbs below has never been built
> at all. They are written down so the shape can be argued about, not so anyone
> implements them yet. Where a verb is implemented, this section gives its real
> current signature rather than an idealised one.

**`rect_batch(items, n, ox, oy, c)`** — many filled rectangles in one call.
`items` is a **flat** sequence of `x, y, w, h, c` quints (flat, not a list of
tuples: one allocation instead of N, which is what makes a few-hundred-span frame
affordable from a script). `n` is how many quints to read, `-1` for all; `ox, oy`
offset every rect; `c` overrides every rect's color, `-1` to use each quint's own.

**`spans(n)`** — a reusable buffer of `n * 5` slots to fill and hand to
`rect_batch`, so a per-frame batch costs no allocation at all. Its existence is
the tell that this group is about dispatch and memory traffic rather than drawing.

These are dispatch verbs rather than drawing features — but they are the ones that
make software 3D viable at all. A raycaster's frame is a few hundred narrow vertical
spans; issuing those one call at a time from a script is what makes raycasting
impossible on an interpreted host rather than merely slow.

**`spr_batch(items, colorkey, scale)`** — many 1 × 1 tiles in one call. `items` is a
sequence of `{tile, x, y}` or `{tile, x, y, flip}`. Semantically identical to calling
`spr` in a loop, and a host may implement it as exactly that.

**`col_batch(items, ...)`** — the same batch, the same pixels, declared as
*columns*. **Not implemented anywhere; this is a proposal, not a description.**

The reason it might need to exist: on reference hardware, tall narrow spans measured
~4× the per-pixel cost of wide ones (~300ns/px against ~74ns/px), and that gap
survived being moved out of a script into a C kernel — so it is memory order, not
dispatch. Every pixel of a 1px-wide span lands in its own cache line. **A cart cannot
choose its memory order; an engine can** — but only if the cart says the batch is
column-shaped. Hence `rect_batch` for wide/boxy spans, `col_batch` for tall thin ones.

**`tri` / `trib`** (§6) and **`sspr`** (§7.1) belong to this same provisional group.

**What is unresolved:**

0. **Whether the dispatch verbs are needed at all.** `spr_batch` was in core 0.1 and
   was moved here, because on the reference console the argument for it turned out
   not to hold: its Lua binding appends sprite quads into the native batch array
   directly, breaking the run only on a state change, so an ordinary `spr` loop
   already compiles to the one batched call `spr_batch` would have produced. It never
   crosses the language boundary the verb exists to avoid. If that is true of any
   competently-bridged host, the whole family is an optimisation the *engine* owes
   the cart rather than a verb the cart owes the engine — and the same question
   should be asked of `rect_batch` before it is promoted.

1. **Whether `col_batch` earns its place.** The ~4× cost is measured; whether
   row-major iteration recovers it is not — and nothing has been built to find out,
   which is why the verb has no implementation. If it doesn't recover, delete the
   verb and accept the stride cost as a hardware fact.
2. **Whether the split should exist at all.** One verb with a shape hint, or an engine
   that infers shape from the spans, may beat two names.
3. **`sspr` has no kernel.** Per-destination-pixel from a script is unusably slow, and
   it is the verb PICO-8 raycasters lean on — it likely needs a native implementation
   before it can be specced honestly.
4. **Whether a higher-level verb is the right level entirely.** Playdate ships a C
   rasterizer (Mini3D) rather than exposing primitives. A textured-column batch, or
   even a `raycast()` over the tilemap, would be dramatically faster and dramatically
   less general. That trade — speed against implementability by others — is the real
   open question, and it is a spec question, not an optimisation one.

---

## 7. Sprites, map, input

### 7.1 Sprites

| verb | effect |
|---|---|
| `spr(n, x, y, colorkey, scale, flip)` | draw sheet tile `n` at `x, y` |
| `spr_batch(items, colorkey, scale)` | draw many 1 × 1 tiles in one call — ⚑ TBD, see §6.1 |
| `sspr(sx, sy, sw, sh, dx, dy, dw, dh, colorkey, flip)` | stretch a sheet **pixel** region to `dw × dh` at `dx, dy` — ⚑ TBD, see §6.1 |

`n` is a sheet tile, **0–511**. `colorkey` is the transparent palette index, `-1` for
opaque (default). `scale` is an integer enlargement, default 1. `flip`: `0` none, `1`
horizontal, `2` vertical, `3` both. A sprite larger than one tile is drawn as its
tiles — adjacent `spr` calls.

`sspr` addresses the sheet in **pixels, not tiles**, and its scale is arbitrary rather
than integer.

**Drawing sprites needs only `spr`.** Many tiles is a plain loop over it; `spr_batch`
is a dispatch shortcut for that loop and is provisional (§6.1), not core 0.1.

### 7.2 Map

| verb | effect |
|---|---|
| `map(mx, my, w, h, sx, sy, colorkey, scale)` | blit a `w × h` region of the tilemap at cell `mx, my` to screen `sx, sy` |
| `mget(x, y)` | tile id at a cell; `-1` for empty or out of range |
| `mset(x, y, tile)` | write a cell; a negative id clears it |

### 7.3 Input

The console defines **logical buttons**. Each host maps its own physical hardware onto
them — a d-pad, a keyboard, a trackball, an on-screen pad. No two implementations need
the same physical controls.

| button | required |
|---|---|
| `left` `right` `up` `down` | **yes** |
| `a` `b` | **yes** |
| `run` | no |

| verb | returns |
|---|---|
| `btn(name, player)` | true while held; `player` defaults to 0 |
| `btnp(name, player)` | true on the frame it was pressed (released → held edge) |
| `players()` | how many controllers are connected. **Always ≥ 1** |

`btnp` fires **once per physical press, with no autorepeat** (§12.2). A cart wanting
repeat implements its own timer.

**Player 0 is always this console's own controls**, so a single-player cart never
passes the argument and never notices this exists. Higher indices read additional
controllers; on a console with one, `players()` returns 1 and `btn(name, p)` for
`p > 0` is always false.

That is deliberate: it means a two-player cart is **portable by construction**. It
asks `players() >= 2` at runtime and offers versus mode or doesn't, rather than being
refused at load time by every console with a single pad. Local multiplayer is core
precisely because it degrades cleanly, and a capability that degrades cleanly should
never be a thing a cart has to declare.

**The host owns exit.** There is no exit button in the console's input model, and no
cart is required to provide one. How a player quits — a held key, a system button, a
window close — is the host's business, and the cart never sees it.

**Optional input**, present only on hosts with the hardware:

| verb | returns |
|---|---|
| `touch()` | `x, y, tapped, held` — nil when there is no pointer |
| `key(code)` / `keyp(code)` | is that ASCII code held / pressed this frame |
| `key()` / `keyp()` | with no argument: the last typed ASCII code, `0` for none |
| `textmode(on)` | switch the keyboard to text input (clean typeable ASCII, autorepeating delete) and back |

`textmode` exists because a game keyboard and a typing keyboard want opposite
semantics (held-key streaming vs. clean characters); hosts whose keyboard has only
one mode implement it as a no-op. While a cart holds `textmode(true)` the host's
own exit gesture may be unreachable (every key is text), so such a cart MUST offer
its own exit via `quit()` (§9).

A cart declares what it *uses* in the manifest's `"input"` list: any of `"buttons"`,
`"touch"`, `"keyboard"`. Hosts use it to decide whether to draw soft controls, and to
tell a player up front which enhancements this device won't provide. It is never a
requirement — a cart that lists `"touch"` still plays on a device without one, by the
rule below.

**A cart MUST be playable with buttons alone.** Touch and keyboard are enhancements. A
cart that cannot be played on a six-button device is not a conforming cart — without
this rule the catalogue splits along hardware lines immediately.

---

## 8. Audio

**4 channels.** Music claims channels from the top — a 1-channel track owns
channel 3, an N-channel track channels `3 … 4−N` — and sound effects round-robin
across whatever music leaves free, so an effect never cuts the background loop.

### 8.1 The data model

The atom is a **note**: `[pitch, wave, vol]`, optionally `[pitch, wave, vol, eff]`.

| field | range | meaning |
|---|---|---|
| `pitch` | `0–95`, or `-1` | semitone index, C0–B7. **57 = A4 = 440 Hz**, equal temperament. `-1` is a rest |
| `wave` | `0–7` | `0` square, `1` triangle, `2` saw, `3` noise, `4` pulse, `5` organ, `6` tilted saw, `7` phaser |
| `vol` | `0–7` | `0` is silent; default `6` |
| `eff` | `0–7` | optional per-note effect (below); omitted means `0` (none) |

**Effects** (PICO-8 numbering, so a ported cart's effect column carries over
verbatim):

| eff | name | behaviour over the note's duration |
|---|---|---|
| `1` | slide | pitch and volume glide from the channel's previous note |
| `2` | vibrato | pitch wobbles ±0.25 semitone (triangle LFO, 7.5 Hz) |
| `3` | drop | frequency falls linearly to 0 |
| `4` | fade in | volume ramps 0 → `vol` |
| `5` | fade out | volume ramps `vol` → 0 |
| `6` | arpeggio fast | cycles the note's group of four steps at 30 notes/s |
| `7` | arpeggio slow | the same at 15 notes/s |

An **SFX** is a short list of notes played in sequence:

```json
{ "speed": 24, "loop": false, "steps": [[30, 3, 5], [26, 3, 3, 5]] }
```

`speed` is **steps per second** (each step lasts `1 / speed` seconds), default 8.
A looping SFX may carry an optional `"loop_start"` (default 0): the whole list
plays once, then `loop_start … end` repeats — a riff with a pickup, PICO-8's
loop range.

A **music track** is an ordered list of pattern **rows**. A row is one SFX id
— or a list of **up to 4** ids, one per channel in order, `-1` for a channel
silent that row:

```json
{ "speed": 4, "loop": true, "pattern": [0, [1, 4], [1, -1, 5], 2] }
```

`speed` is **rows per second** (fractional values are legal), default 4;
`loop` defaults true. Channel positions are stable across rows — channel `j`
stays on the same voice, which is what lets a slide carry across a row
boundary. Row channel `j` plays on voice `3 − j`.

A track may carry an optional `"row_secs"`: a list parallel to `pattern` of
**per-row durations in seconds**, overriding the uniform `speed` clock. An
entry of `0` holds that row forever (its looping channels keep playing;
`music()`/`music_stop()` still end it). This is what an imported PICO-8 song
needs — there a pattern lasts as long as its first *non-looping* channel
(or, when every channel loops, its slowest one), and that reference tempo
changes row to row.

Both live in the cart's `sounds.json`:

```json
{ "sfx": [ ... ], "music": [ ... ] }
```

### 8.2 Verbs

| verb | effect |
|---|---|
| `sfx(n, chan)` | play bank effect `n`; `chan` optional, otherwise round-robin the channels music leaves free |
| `beep(freq, dur)` | a tone at `freq` Hz for `dur` seconds (default 0.15), square wave at vol 6 |
| `music(track, loop)` | start a music track (channels claimed from the top, §8); `loop` defaults true |
| `music_stop()` | stop music |
| `sound_stop(chan)` | stop one channel, or all if omitted |
| `volume(level)` | master output level |

A host with no audio hardware implements these as no-ops and still conforms — silence
is a valid rendering. It MUST NOT error, and a cart MUST NOT depend on audio for
playability.

### 8.3 Synthesis

Waveforms are generated, not sampled, and mixed to signed 16-bit mono; voices
sum with each note scaled by `vol / 7`. The eight shapes: square (50% duty),
triangle, saw, LCG noise, pulse (⅓ duty), organ (triangle plus a quieter
octave-up triangle), tilted saw (rise over ⅞ of the period, fall over ⅛), and
phaser (two triangles, the second detuned to `freq × 127/128`, summed — a slow
beat). These are engine-native shapes, deliberately *near* PICO-8's instruments
rather than clones of them.

Audio is explicitly **not** covered by pixel conformance. Two hosts will not produce
bit-identical samples and are not required to — but a host SHOULD implement the
effect and multi-channel semantics of §8.1, since imported music depends on them
musically.

---

## 9. State and utility

| verb | effect |
|---|---|
| `time()` | milliseconds since the cart started |
| `pmem(i)` / `pmem(i, v)` | persistent save slots — read / write an integer |
| `cfg(key, default)` | read a value from the cart's `config.json` |
| `rnd(n)` | random float in `[0, n)`, default `n = 1.0` |
| `flr(x)` | floor to integer |
| `quit()` | end this cart; the host returns to wherever it was launched from |
| `W`, `H` | canvas dimensions — read these, do not assume 320 × 240 |

`quit()` does not replace the host-owned exit (§7.3) — the player can always leave
a cart without it. It exists so a cart can end *itself* (a menu's EXIT entry, a
game-over screen), and it is the required exit for a `textmode(true)` cart.

`pmem` has **64 integer slots**, persisted per cart. Hosts MAY defer the write; they
MUST persist before the cart exits.

`config.json` is a flat map of values a person can edit without touching code — the
cart's own tuning surface, not a system feature.

---

## 10. Extensions

Optional features. A cart requiring one lists it in the manifest's `"extensions"`
array; a host that doesn't implement it refuses the cart cleanly rather than crashing
partway in.

The two below are **standard extensions** — optional, but specified here so that two
consoles implementing `layers` implement the same `layers`.

A console may also define **its own** extensions for hardware or features core says
nothing about — a radio (`espnow`), a second cart language, an on-device authoring
format, a windowing shell. Those MUST be namespaced by the implementation
(`vendor.feature`, e.g. `moybyte.scenes`) so they can never collide with a future
standard extension, and a cart using one is non-portable by construction. That is a
legitimate trade an author makes deliberately, not an accident the format allows.

**The namespace is on the extension's name, not on its verbs.** `"extensions":
["moybyte.tables"]` may perfectly well grant a global called `table()`. Lua globals
have no namespaces, and requiring `moybyte.table()` at the call site would make the
cart's code — rather than its manifest — the place portability is declared. The
manifest is the honest place: one line says what this cart needs, and a host can
refuse it before a single frame runs.

### `layers`

Off-screen buffers for scrolling worlds — draw a wide level once, window-copy it each
frame instead of re-rendering. `make_layer(w, h)` returns a layer speaking the full
drawing API; `draw_layer(layer, cx, cy)` blits its visible window; `background(x)`
declares a backdrop the host repaints automatically each frame. Costs 75 KB per
full-screen layer (§1.1).

### `viewport`

`view(w, h)` declares a logical viewport smaller than the canvas; the host composites
that centered region at the largest integer scale that fits. This is how a converted
128 × 128 PICO-8 cart fills a screen instead of sitting in a 320 × 240 letterbox.

### Not here: networking

Console-to-console play is **not** a standard extension and is not core. A minimal
"send a small message, receive a callback" contract looks portable on paper, but the
transports underneath it — a mesh radio, WiFi, BLE, a browser socket — differ in
latency, reliability, peer discovery and message size by orders of magnitude, and a
cart written against one will not behave on another. Specifying it would promise a
portability that cannot be delivered.

So networking belongs in vendor space: `espnow`, `vendor.net`. A cart using it is
non-portable and says so. This may be revisited once two consoles have shipped
networked carts and there is something real to generalise from.

*(Local multiple controllers are a different thing entirely, and are core — see §7.3.)*

---

## 11. Conformance

An implementation conforms when it runs the conformance suite and produces
**pixel-identical** output.

The suite is a set of carts, each exercising one area — primitives, sprite flips and
scales, clip and camera interaction, palette remaps, text, map blits, input edges —
plus golden frames. A runner diffs your output frame by frame.

**The golden frames are generated by the WebAssembly player** (`runner/`), which is
therefore the tiebreaker for any disagreement between this document and observed
behaviour. Where the two conflict, **the spec text is wrong and gets fixed** — but
implementations are tested against the player.

The player is the reference precisely because it is the build that follows §4.2: its
Lua is compiled `LUA_32BITS`, like the hardware consoles. A host may render the suite
through any tooling it likes, but frames captured from a 64-bit-Lua build are not
golden — float-heavy carts will drift from them in the last digits (§4.2).

Conformance also tests the §4.1 sandbox ceiling: a cart that reaches `io` must fail on
every conforming host. Audio is excluded (§8.3), and so is everything in §6.1 until it
leaves TBD.

---

## 12. Decisions worth arguing with

Everything outside §6.1 is decided. These are the ones where a reasonable person would
decide differently, recorded with reasoning so the argument can be specific.

### 12.1 — No display-time palette.

PICO-8 has two palettes: draw-time remap, and a
screen palette applied at flush. This spec has only the first. The second doubles the
palette state every primitive must consult and mainly buys full-screen flash effects,
which a cart can do by other means. **Cost:** converted PICO-8 carts using
screen-palette tricks need the converter to rewrite them, and some can't be. This is
the most likely thing to get added in 0.2.

### 12.2 — `btnp` has no autorepeat.

PICO-8 repeats a held button after ~15 frames at
~4-frame intervals. This spec fires once per press. Autorepeat in the console means
every host must match the rate exactly or menus feel different everywhere; a cart that
wants it can write four lines. **Cost:** converted PICO-8 carts relying on repeat for
menu navigation feel wrong until the converter injects a shim.

### 12.3 — Sprites are 16 colors, primitives are 64.

One hex nibble per pixel is
PICO-8's sheet format exactly, and that compatibility is what makes converting the
existing back catalogue nearly free. Cart-supplied palettes (§2.2) mean the constraint
is *sixteen at a time*, not sixteen specific colors. **Cost:** an artist cannot use
more than 16 distinct colors within one sprite sheet, only in backgrounds and shapes.

### 12.4 — 400 KB is the memory floor.

Derived from the allocations in §1.1 with
headroom, not negotiated, and not yet profiled against a running console. A host that
can't free that while a cart runs can't run carts. Since any RAM kind counts (§1.1),
a board with external PSRAM clears it trivially; the floor only bites SRAM-only
parts. **Cost:** it rules out the smallest of those, deliberately — a lower floor
would mean a smaller screen, a smaller sheet or a smaller heap promise to carts,
and those are worse trades.

### 12.5 — 512 tiles, but only 254 placeable on a map.

Keeping map cells at one byte
(storing `tile_id + 1`, so a zeroed map is blank) is worth more than a uniform
addressing range: maps stay half the size and stay readable. The sheet grows where the
real pressure is, which is sprite and animation art. **Cost:** a boundary an author has
to learn — `spr` reaches tiles the map editor can't place.

### 12.6 — No direct framebuffer access.

TIC-80 exposes raw VRAM, which makes any
effect possible and makes the pixel format part of the cart contract — a cart then
writes to *that* framebuffer rather than *a* framebuffer, and hosts lose the freedom to
render at a different depth, scale or byte order. This spec keeps the canvas opaque and
covers the cases raw access was wanted for with shaped verbs instead (§6.1).
**Cost:** effects whose *logic* is genuinely per-pixel — plasma, fire, tunnels — cannot
be written as carts. That is the deliberate boundary.

---

## 13. Versioning

`0.x` is unstable; anything may change. `1.0` freezes the verb table and the cart
format. After 1.0, additive changes bump the minor version and carts declare the
minimum they need via `format`.

## 14. Governance

Maintained by one editor until two independent implementations pass conformance, at
which point it moves to a neutral home with the implementers as maintainers. The
reference implementation and the conformance suite are the deliverables; nobody is
asked to adopt anyone's code.

## 15. Future bindings

The verb table above is the contract; Lua is the **first binding of it**, not its
definition. A second binding (a `"runtime"` field in the manifest, as the reference
implementation already does for its dual runtimes) can be added without a second
document.

WebAssembly is the obvious candidate and has been measured on reference hardware:
**interpreted WASM runs at ~1.09× Lua** — not worth a runtime — while **AOT-compiled
WASM is ~16×**. But AOT carries a constraint fatal to §3 as written: on that hardware
AOT code must be mapped on the instruction bus from its own flash partition, so a
cart's compiled code **cannot be read out of a cart folder**. Installing one means
writing to a scratch partition, with flash wear, and per-architecture compilation
besides — which also rules out editing a cart and pressing play.

So a WASM binding is a plausible *porting and distribution* tier for compiled games,
and a poor fit for authored ones. Recorded here so it isn't rediscovered, not proposed
for 0.1.
