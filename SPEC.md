# moy core 0.1 — the portable console spec

> **Status: DRAFT 0.1.** Everything outside §6.1 is decided and implemented — it
> describes a console that exists and runs games today, not a design sketch.
> **§6.1 (the 3D verbs) is provisional**: its membership is settled and its
> semantics are frozen, but nothing in it is core 0.1 until each verb clears the
> promotion gates stated there. Decisions worth arguing about are collected in
> §12 with their reasoning.

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
| Screen | **320 × 240**, palette-indexed; a cart may declare a smaller canvas (§3.1) |
| Palette | **64 entries** (§2), indices 0–63, cart-replaceable |
| Sprite sheet | **512 tiles** of 8 × 8, drawn from palette indices **0–15** |
| Tilemap | one grid, cells hold a tile id 0–254 |
| Audio | **4 channels**, 8 waveforms, per-note effects (§8) |
| Tick | **30 Hz** guaranteed; 60 Hz opt-in (§5) |
| Language | **Lua 5.4**, sandboxed (§4) |
| Origin | top-left, `+x` right, `+y` down |

The canvas defaults to **320 × 240**. A cart wanting a chunkier look may declare a
smaller raster in its manifest — `"canvas": "160x120"` or `"canvas": "128x128"`
(§3.1) — and then plays entirely in it: every verb clips to it and `W`/`H` report
it (§9). The set is **closed** — these three sizes, not arbitrary dimensions — so
a host still provisions for a fixed-size machine (§1.1) and can pick its scaler
per size ahead of time. A `canvas` value outside the set MUST be refused like an
unknown `runtime` (§3.1): running a cart at a size it did not ask for would break
every coordinate in it.

A host whose physical display does not match the canvas scales and/or letterboxes
the console raster onto its glass. The cart never learns the physical resolution.
Integer scaling is recommended; the choice is the host's.

### 1.1 Memory the host must provide

The console is a fixed-size machine. A conforming host reserves this for it, however
it likes — statically, from a pool, or by shutting down other subsystems while a cart
runs:

| allocation | size | note |
|---|---|---|
| Framebuffer | **75 KB** | 320 × 240 at one byte per index; a smaller declared canvas uses a prefix of the same reservation. A host rendering direct to RGB565 pays 150 KB instead — its choice, not the cart's |
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
| `canvas` | no | raster size: `"320x240"` (default), `"160x120"` or `"128x128"` — see §1 |
| `input` | no | input groups the cart reads — see §7.3 |
| `palette` | no | 64 RGB hex strings replacing the default table — see §2.2 |
| `extensions` | no | optional features required — see §10 |
| `runtime` | no | which language binding `main` is written in, default `"lua"` — see §15 |
| `icon` | no | sheet tiles to show this cart by in a list — see §3.4 |

A host MUST ignore manifest fields it does not recognise. Implementations hang
vendor metadata there (the reference console records editor state in fields of its
own), and future minor versions may add fields — neither may break an existing host.

**`runtime` and an out-of-set `canvas` are the exceptions, refused rather than
ignored** (for `canvas`, see §1). Lua is
core's only binding, so `"runtime"` absent or `"lua"` is the portable case and every
conforming host runs it. A host that does not implement the named binding MUST
refuse the cart cleanly, exactly as it refuses an unimplemented extension (§10) —
never ignore the field and try to execute `main` anyway. Ignoring it is the one
reading that fails badly: the host would hand a script in another language to its
Lua VM and report a syntax error in the author's code, rather than the truth, which
is that this console cannot run this cart. A cart declaring any other `runtime` is
non-portable by construction, the same trade a vendor extension makes.

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

### 3.4 How a cart looks in a list

A host that shows carts — a launcher, a shelf, a picker — needs something to draw
for each one. The manifest's `"icon"` names sheet tiles the cart already contains:

```json
"icon": [4, 2, 2]
```

`[tile, w, h]` — the `w × h` block of 8 × 8 tiles whose top-left is `tile`, laid out
on the sheet exactly as §3.2 addresses it. A bare integer means `1 × 1`. Absent, the
host draws whatever it likes; a cart is never *required* to have one and no host is
required to honour it.

**`w` and `h` are each 1 to 4** — 8 × 8 up to 32 × 32 pixels. The bound is what makes
the field safe to honour: a launcher decodes *many* icons at once, and an unbounded
block would let one cart name the whole 128 × 256 sheet, turning a grid of thirty
carts into megabytes a host never budgeted for (§1.1). At the ceiling, thirty icons
are 30 KB. Anything larger is asking for cover art, which §12.7 defers on purpose.

An icon outside that range, or naming tiles past the sheet, is **ignored** — the host
falls back to choosing for itself. It is not refused: a cart with a bad icon is still
a perfectly good cart, and unlike `extensions` (§10) or `runtime` (§15) nothing about
running it is wrong. Cosmetic fields degrade; capability fields refuse.

How large the icon is *drawn* is the host's business, like everything else about a
shelf. Hosts SHOULD preserve its aspect ratio and SHOULD scale by integer factors, for
the same reason §1 recommends it for the raster.

This costs no new file, no new codec, no colour rules beyond the sheet's, and no
reserved tiles — the author points at art already drawn. It is a **pointer, not an
image**, which is the whole reason it can sit in core.

It is deliberately explicit rather than a convention like "hosts use tile 0". Tile 0
is blank by convention across the entire PICO-8 catalogue — that convention is why
map cell `00` means empty (§3.3) — so a rule resolving to tile 0 would render nothing
for every converted cart. A field that must be named cannot be silently wrong.

Cover art — the large, authored, promotional image a store would show — is
deliberately **not** here. See §12.7.

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
| `tri(x1, y1, x2, y2, x3, y3, c)` | **filled** triangle — provisional, see §6.1 |
| `trib(x1, y1, x2, y2, x3, y3, c)` | triangle **outline** — provisional, see §6.1 |
| `tline(x0, y0, x1, y1, u, v, du, dv, ck)` | textured line sampled from the map — provisional, see §6.1 |
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
glyph, one byte per **column** left to right, LSB = top row.

**`print` walks its argument one BYTE per cell**, not one character. Bytes outside
`0x20`–`0x7F` draw nothing and advance 8px like any glyph, so a two-byte UTF-8
character occupies two blank cells rather than one. This is not a preference: a
Lua string *is* a byte string (§4), so any host that decoded first would advance
the cursor differently from one that did not, and the same cart would lay out
differently on a desktop simulator and a handheld. A cart wanting non-ASCII text
draws it from its own sheet.

`font.bin` is MicroPython's `font_petme128_8x8`, MIT-licensed — shipping the
glyph data means shipping that notice. See `THIRD_PARTY.md`.

### 6.1 The 3D verbs — provisional, membership settled

> **The set is decided; the verbs are provisional.** `tri`, `trib` and `sspr` are
> implemented in every reference implementation and checked by the suite's
> provisional scene; `tline` is implemented in the reference library and the C
> core, golden-checked, and not yet on a device. None
> are core 0.1: each is promoted by the gates at the end of this section, on
> evidence rather than argument. The batch verbs that used to fill this section
> are **deleted**, and the measurements that deleted them are recorded below so
> they are not reinvented.

**The membership rule.** A verb belongs here only if, without it, a cart would
have to run a script loop that scales with **pixels**. Turning many calls into
one is never a reason — batching is the engine's duty, settled below. Each verb
exists because the cart holds information the host cannot infer — where the
triangle is, what the camera sees this scanline — and hands it over in O(calls),
with every per-pixel loop on the host's side of the boundary.

**`tri(x1, y1, x2, y2, x3, y3, c)`** — filled triangle. Vertices sorted by y,
both edges walked with **floor division** — not C truncation, which differs by
one for negative numerators and costs a whole column on a leaning edge — and one
inclusive horizontal span emitted per scanline. Four implementations already
agree on every pixel of this; the text records what the goldens enforce.

**`trib(x1, y1, x2, y2, x3, y3, c)`** — the three edges, exactly `line`'s pixels.
Fails the membership rule on its own (it *is* three `line` calls) and is kept for
symmetry with `rect`/`rectb` and `circ`/`circb`, at no implementation cost.

**`sspr(sx, sy, sw, sh, dx, dy, dw, dh, colorkey, flip)`** (§7.1) — stretch a
sheet **pixel** region to an arbitrary destination rect. Nearest-neighbour; the
source texel of destination column `i` is `(i * sw) // dw` — exact integer
arithmetic, nothing to round. This is the raycaster's textured wall slice at
`dw = 1`, and non-integer sprite scaling everywhere else.

**`tline(x0, y0, x1, y1, u, v, du, dv, colorkey)`** — draw exactly the pixels
`line(x0, y0, x1, y1)` would draw; before each pixel, sample the **map** at texel
`(u >> 16, v >> 16)`, then advance `u += du`, `v += dv`. All four texture
arguments are **16.16 fixed-point integers** — a cart computes in floats and
multiplies by 65536 at the call.

Sampling: the map is read as a virtual texture of `w×8 by h×8` pixels (a full
128 × 128 map is 1024 × 1024). Texel `(px, py)` lives in cell
`(px >> 3, py >> 3)`; an empty cell draws nothing for that pixel (the cursor
still advances); a placed tile draws its sheet pixel `(px & 7, py & 7)`, through
`pal`, `palt` and the optional `colorkey` exactly as `spr` would. Texture
coordinates wrap modulo the map's pixel size. The screen endpoints are
camera-relative and clipped like any `line`; the texture walk is not — camera
moves where the line lands, never what it samples.

Fixed point is the load-bearing choice. With float texture steps, a JS host, a
MicroPython host and a C host would round differently in the last bit and the
golden frames would stop being enforceable; with 16.16 integers every
implementation performs identical arithmetic. And sampling the **map** rather
than the sheet is what makes the verb worth having: 1024 × 1024 of texture is a
racing track, and the sheet is still reachable through it by pointing cells at
tiles.

`tline` is the Mode 7 verb. Along one scanline of a perspective ground plane the
texture step is constant — all the perspective lives in how `du, dv` change
*between* scanlines — so a rotating, scaling floor is ~120 calls each frame, with
every per-pixel cost in the host's kernel. The same call drawn vertically
textures a raycaster's floor and ceiling columns.

**What the set covers, and what it deliberately does not.** The measured frame
budgets (reference console, 2026-07/08; its slower board is the floor the spec
budgets against):

| technique | shape | floor-board budget |
|---|---|---|
| Mode 7 plane | ~120 `tline` calls | **~8 ms for a half-screen plane, measured on the FASTER reference board** (~210 ns/texel). The first kernel measured ~25 ms — two 64-bit software modulos per texel — and this row is what caught it; the fix (reduce once, wrap by conditional subtract) moved no pixel, which the golden proves. The floor board's own row is still owed |
| raycaster | script DDA + `sspr`/`rect` columns | measured on glass: ~32 fps full-res, past 60 at half-res |
| flat-shaded polygons | `tri` per face | dispatch + fill, small triangles near the call floor |
| scaled sprites, billboards | `sspr` | sub-ms each |

These are **call-bounded**: cost scales with verbs issued, and the host owns
every pixel. What the set does not cover is **step-bounded** work whose output is
data-dependent per sample — voxel-terrain rendering (Comanche), general textured
3D, per-pixel effects. No verb fixes those: the cost is the cart's own
interpreted loop. They belong to a vendor extension (§10) or to a compiled-cart
binding (§15), and a cart author should know that *before* building — which is
what this table is for.

**Promotion gates.** A provisional verb becomes core when, and only when:

1. **It has a native kernel in the reference console.** The floor board runs the
   interpreted fallbacks at 7.5 ms per `tri` and 36 ms per small `sspr` — a verb
   slower than the frame it draws into cannot honestly be specced. (All four
   have C kernels in `libmoy/`; the reference console still owes its own for
   `tri`, `sspr` and `tline`.)
2. **The suite has golden frames for it** beyond the provisional scene, promoted
   into the counted set.
3. **It has a measured row in the reference bench on both reference boards**, so
   the first cart author to lean on it reads a cost, not a hope.

**The deleted verbs, and the measurements that deleted them.** Recorded so the
next reader does not re-derive them:

- **`spr_batch`** — on the reference console an ordinary `spr` loop already lands
  in the native batch array, breaking the run only on a state change. The verb's
  one job — avoiding the language boundary — was already done by the engine.
- **`rect_batch` / `spans`** — same fate, measured later: once the reference
  console gated its root canvas through C-side appends, a plain `rect` loop costs
  ~26 µs/call on the floor board and the raycaster that motivated the batch ships
  without it. **Batching is the host's duty.** A conforming host is expected to
  make repeated verb calls cheap; a cart is never asked to pre-pack its geometry.
- **`col_batch`** — built and A/B-measured against `rect_batch` on identical
  spans: **0.6×** — 56 % *slower* — because its row-major membership scan cost
  more than the cache locality it bought. Its motivating figure, previously cited
  in this section ("narrow spans cost ~300 ns/px, ~4× wide fills"), was a
  subtraction artifact: measured directly, narrow spans cost ~120 ns/px against
  ~74, a ~1.6× penalty too small for any iteration order to pay for itself.
- **`raycast()` and other engine verbs** — resolved out on principle: a verb that
  takes a camera and returns a finished frame is an engine, and an engine behind
  a verb is a vendor extension (§10) or a library inside a compiled cart (§15),
  never core. Core verbs are the primitives every genre shares.

---

## 7. Sprites, map, input

### 7.1 Sprites

| verb | effect |
|---|---|
| `spr(n, x, y, colorkey, scale, flip)` | draw sheet tile `n` at `x, y` |
| `sspr(sx, sy, sw, sh, dx, dy, dw, dh, colorkey, flip)` | stretch a sheet **pixel** region to `dw × dh` at `dx, dy` — provisional, see §6.1 |

`n` is a sheet tile, **0–511**. `colorkey` is the transparent palette index, `-1` for
opaque (default). `scale` is an integer enlargement, default 1. `flip`: `0` none, `1`
horizontal, `2` vertical, `3` both. A sprite larger than one tile is drawn as its
tiles — adjacent `spr` calls.

`sspr` addresses the sheet in **pixels, not tiles**, and its scale is arbitrary rather
than integer.

**Drawing sprites needs only `spr`.** Many tiles is a plain loop over it — a
conforming host makes that loop cheap (§6.1's batching note), and the batch verb
this section once pointed at is deleted for exactly that reason.

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
| `1` | slide | frequency and volume glide from the channel's previous note — linear in **Hz**, not semitones, as in PICO-8 |
| `2` | vibrato | pitch wobbles ±0.25 semitone (triangle LFO, 7.5 Hz) |
| `3` | drop | frequency falls linearly to 0 |
| `4` | fade in | volume ramps 0 → `vol` |
| `5` | fade out | volume ramps `vol` → 0 |
| `6` | arpeggio fast | cycles the note's group of four steps at 30 notes/s — 60 on a fast SFX (15+ steps/s) |
| `7` | arpeggio slow | the same at 15 notes/s — 30 on a fast SFX |

A note with `vol` `0` but a real pitch is a **keyed rest**: silent, yet it still
becomes the channel's previous note — the origin a following slide glides from.
PICO-8 works this way (every tracker slot has a key), so ported slides land
right. Only pitch `-1` leaves the slide origin untouched.

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
triangle, saw, noise (an LCG random walk through a one-pole low-pass whose
cutoff tracks the note, with a bass lift at low keys), pulse (⅓ duty), organ
(a triangle with a quieter octave-up partner), tilted saw (rise over ⅞ of the
period, fall over ⅛), and phaser (two triangles, the second detuned to
`freq × 109/110`, summed — a slow beat). Instrument loudness is deliberately
**unequal**, following PICO-8's own mix — the triangle family peaks at about
twice the square family — because ported music is balanced against exactly
that; render them equal and every square lead shouts down its accompaniment.
These shapes follow PICO-8's synthesis (as reverse-engineered by zepto8 and
fake-08) closely, but exact sample equality is still not asked of anyone
(below).

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

`pmem` has **256 slots**, each holding one **signed 32-bit integer** (−2 147 483 648
to 2 147 483 647), persisted per cart. That is exactly what §4.2 makes a Lua integer,
which is where every stored value comes from and returns to — a wider slot would
accept numbers the cart could not read back. Hosts MAY defer the write; they MUST
persist before the cart exits.

`config.json` is a flat map of values a person can edit without touching code — the
cart's own tuning surface, not a system feature.

---

## 10. Extensions

Optional features. A cart requiring one lists it in the manifest's `"extensions"`
array; a host that doesn't implement it refuses the cart cleanly rather than crashing
partway in.

Declaring is for *requiring*. A cart may instead use an extension
opportunistically — check the verb exists before calling it (`if view ~= nil
then view(...) end`) and declare nothing. Such a cart runs on every host,
degraded where the extension is absent, lit up where it isn't; an extension's
verbs simply do not exist as globals on a host without it.

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
Declaring `"canvas": "128x128"` (§3.1) reaches the same look through the manifest —
the raster itself shrinks and `W`/`H` change with it — with no extension involved;
`view` is for choosing (or changing) the region at runtime while keeping the full
canvas underneath.

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
every conforming host. Audio is excluded (§8.3), and so are the §6.1 verbs until each
clears its promotion gates — the suite exercises them in a provisional scene that is
reported but not counted.

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
be written as Lua carts. That is the deliberate boundary, and it is a statement about
*this* binding: a compiled-cart binding (§15) is where that boundary would move, with
a framebuffer in the cart's own linear memory rather than raw access to the host's.

### 12.7 — Cover art is deferred, and the icon is a pointer.

PICO-8 ships a `__label__`: a 128 × 128 authored image, captured from the screen with
a keystroke, in the same hex-nibble format as its sprite sheet. It is tempting to copy
and it is not the same problem. That label exists because a PICO-8 cart **is** a PNG —
the label is the picture of the cartridge you distribute. A moy cart is a folder, so
the medium that forced the feature isn't there.

Underneath the one word "thumbnail" are two requirements with opposite costs. An
**icon** must exist for every cart or lists have holes in them; §3.4 answers that for
the price of one optional manifest field. A **cover** is optional, promotional, and
only pays for itself once there is a catalogue to browse — and every way to spec one
today is a bad trade. Hex nibbles are free on the parser but 16 colors and
uncompressed: a full-screen image is 75 KB of text against a 400 KB memory floor
(§12.4). An indexed-plus-RLE format means every implementer writes a second codec.
PNG means a zlib decoder on a microcontroller, in a format whose data files are
otherwise all readable text.

So: no cover in 0.1. §14 says this document moves to a neutral home once a second
implementation passes conformance, and an image format is exactly what should be
settled *with* that implementer rather than guessed at alone. Until then it belongs
in an extension.

**Also ruled out, permanently:** a host-captured screenshot as a format feature. A
host can already run a cart, grab a frame and cache it — that needs no spec at all, so
it must not be in one. It is also the wrong artefact: an automatic frame is arbitrary,
and the reason PICO-8 binds label capture to a keystroke is that the author should
choose how their game is represented.

**Cost:** a store built on moy 0.1 has only 8 × 8 tile art to lay out, which will look
sparse next to a storefront with key art. That is the right way round — a missing
cover is a design problem later, a wrong image format is a compatibility problem
forever.

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
document. What a host owes a binding it does not implement is settled in §3.1: a
clean refusal, never an attempt to run the script anyway.

WebAssembly is the settled candidate, measured on reference hardware (a 6502
interpreter core — branch-heavy dispatch, a VM's worst case — line-faithful in Lua
and C, identical cycle counts out of every runtime): **interpreted WASM runs at
~1.09× Lua**, which does not justify a runtime, while **AOT-compiled WASM is ~16×,
and ~91× on straight-line arithmetic**. The doctrine that follows from those two
numbers is recorded here so it is not re-litigated:

- **Two tiers, two contracts.** Script carts draw through verbs and the host owns
  every pixel — §6.1's set is sized for exactly that. Compiled carts bring their
  own rasterizer and need one thing the verb table cannot give: a framebuffer in
  the cart's linear memory that the host blits once per frame. Reaching pixels
  through a per-pixel import pays a language-boundary trampoline 76,800 times a
  frame and is dead at any VM speed — **fast 3D is gated on the framebuffer
  contract, not on the runtime**. §12.6's no-framebuffer rule is a statement
  about the Lua binding; this is where that boundary moves, without ever exposing
  the *host's* framebuffer.
- **The portable artifact is `main.wasm`, alone.** AOT is a host-side install
  step, invisible to the cart: on reference hardware with no exec-capable heap,
  AOT text must be XIP-mapped from its own flash partition, so installing a
  compiled cart is a real install, with flash wear — and a browser host needs
  none of it, JIT-ing the same `.wasm` it was handed. A cart shipping
  per-architecture binaries is the model this binding exists to reject.
- **Lua does not compile into the fast tier.** The 16× comes from static types,
  not from WASM — the 1.09× interpreter *is* the control. The road from a Lua
  cart to a fast one is a port: same verbs, same tick, same assets, and the
  conformance suite can hold the twins pixel-identical. (A typed Lua dialect —
  Pallene, Nelua — could plausibly ride the same pipeline; noted, not proposed.)
- **Source beside the `.wasm` is welcome and never required.** A required-source
  rule is unverifiable, and the tier exists for ports and commercial work; the
  always-readable tier is the Lua cart, whose `main.lua` *is* the source.

The full ABI draft — module shape, import table, the framebuffer contract,
determinism profile, distribution, open items — is `proposals/wasm-runtime.md`.
Not part of 0.1.
