# moy core 0.3 — the portable console spec

> **Status: DRAFT 0.3.** Every verb here is decided and implemented — this
> describes a console that exists and runs games today, not a design sketch.
> The 3D verbs (§6.1), provisional through 0.2, are core as of 0.3. Decisions
> worth arguing about are collected in §12 with their reasoning. §16, the
> WebAssembly binding, is optional: a host implements it or refuses its carts.

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
| Language | **Lua 5.4**, sandboxed (§4); WebAssembly, an optional second binding (§16) |
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
| One layer (§6) | **75 KB** | a full-screen off-screen buffer; more than one is host-dependent |
| | | |
| **Total** | **≈ 400 KB** | with headroom |

**Measured, not derived** (2026-08-13, the reference implementation): a deliberately
heap-heavy cart — 200 actors each carrying a closure, per-frame string garbage, a
full-screen layer, a 128 × 128 map — reaches **88.8 KB** of Lua heap and **295 KB**
in total, layer included. An ordinary fully-bridged cart uses about 41 KB of heap.
So 192 KB for the heap is generous rather than tight, and the floor has room for the
layer that used to sit outside it.

**One layer is guaranteed; further ones are not.** A host may decline, and
`make_layer` returns nil when it does (§6) — an allocation that can fail is an
ordinary runtime condition a cart tests for, unlike a verb that does not exist.

**This is a floor, not a target.** A host that cannot free 400 KB while a cart runs
cannot conform — freeing it is the implementer's problem, and a "game mode" that
suspends other subsystems for the duration is a perfectly good way to solve it.

**The kind of RAM is not specified.** Internal SRAM, external PSRAM, or any mix
qualifies — if `_update` and the drawing verbs hold the tick rate against it, it
counts. That makes the floor trivial on PSRAM-equipped boards (most ESP32-class
devices carry megabytes) and binding only for single-die parts: 400 KB deliberately
excludes the smallest SRAM-only microcontrollers (§12.4). Placement is a quality
concern, not a conformance one, and a cart can observe none of it. Which RAM to put
what in is worth measuring on your own board — `RATIONALE.md`, "Memory — 400 KB", has
what the reference implementation measured on its.

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
For an implementer the number that matters is the one it implies: the whole
index→native-pixel table is 128 bytes as an RGB565 LUT, small enough for fast memory
on any host, and the canvas stores one byte per pixel whatever the count.

The *colors* are not fixed by this spec — see below. Why sixty-four and not another
number: `RATIONALE.md`, "Palette — 64 entries".

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
  flags.moyflags     optional — one flag byte per tile
  sounds.json        optional — the audio bank
  config.json        optional — author-exposed tuning values
  …more .lua         optional — further scripts, listed in `sources` (§4)
```

That folder is the whole format. How the folder *travels* — a zip, a tarball, a
git clone, a directory on an SD card — is packaging, and this spec says nothing
about it for the same reason it says nothing about filesystems (§0). A host that
wants to accept an archive unpacks it and hands the console a folder.

A compiled cart (§16) is the same folder with a WebAssembly module in place of its
Lua; §16.1 says what changes.

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
| `main` | no | the cart's own script, default `main.lua` |
| `sources` | no | every script the host loads, in order; default `[main]` — see §4 |
| `fps` | no | `30` (default), `60`, or `"free"` — see §5 |
| `canvas` | no | raster size: `"320x240"` (default), `"160x120"` or `"128x128"` — see §1 |
| `input` | no | input groups the cart reads — see §7.3 |
| `palette` | no | 64 RGB hex strings replacing the default table — see §2.2 |
| `extensions` | no | optional features required — see §10 |
| `runtime` | no | which language binding `main` is written in, default `"lua"` — see §15 |
| `icon` | no | sheet tiles to show this cart by in a list — see §3.4 |

A host MUST ignore manifest fields it does not recognise. Implementations hang
vendor metadata there (the reference console records editor state in fields of its
own), and future minor versions may add fields — neither may break an existing host.

**`runtime`, `sources` and an out-of-set `canvas` are the exceptions, refused or
implemented rather than ignored** (for `canvas`, see §1; for `sources`, §4). Lua is
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

### 3.5 flags.moyflags

One byte per tile, **512 tiles** in tile order, as hex pairs: sixteen lines of
sixty-four digits, whitespace ignored. A short file leaves the remaining tiles
zero; an absent file is all zero. It is the tile-tagging idiom of both consoles
this format courts — *solid*, *spike*, *coin*, *layer 2* — read by `fget`, written
by `fset` and consulted by `map(..., layers)` (§7.1, §7.2). PICO-8's `__gff__` is
its first 256 tiles, byte for byte.

A sidecar rather than a manifest field because it is data with the sheet's
shape, and rather than a block in `sprites.moygfx` because that file has one
concern already. How a host lets an author set the bits — dots in a sprite
inspector, a text editor — is the host's business, like every other authoring
surface.

---

## 4. Program model

A cart is Lua 5.4. It defines up to three global functions and calls the console
verbs, which are pre-injected as globals. **No `require`, no imports** — a cart
never loads code; the host loads what the manifest lists, before `_init` runs.

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

**More than one file.** A cart may split its code. The manifest's `"sources"`
lists every script, and the host runs them **in that order**:

```json
  "main": "main.lua",
  "sources": ["p8.lua", "main.lua", "extra.lua"]
```

Omitted, it is `[main]`, so a one-file cart says nothing and nothing changes for
it. `main` MUST appear in `sources`; it is not the first entry but the *authored*
one — which file an editor opens, which file a crash's line number belongs to —
and the entries around it are the prologue and epilogue the cart was built with.
A `sources` that omits `main`, or names a file the folder does not hold, is a
broken cart and gets §3.1's clean refusal, not a partial run.

**Each script is its own chunk.** `local` does not cross a file boundary, so
files share the way a cart already talks to the console: through globals. A
prologue publishing a helper writes `function helper()`, not `local function
helper()`. The alternative — pasting the files together so locals do carry —
is rejected, and §12.8 says why.

This is still not importing. The cart cannot reach `load` or `require` (§4.1)
and does not decide what runs: the manifest declares a list, the host executes
it. Two hosts given the same folder load the same files in the same order.

### 4.1 Sandbox

The available Lua standard library is exactly:

**`base`** (minus `load`, `loadstring`, `loadfile`, `dofile`, `require`,
`collectgarbage`),
**`math`**, **`string`**, **`table`**, **`coroutine`**.

Absent entirely: `io`, `os`, `debug`, `package`.

Every one of those reaches the host; `coroutine` does not, so a cart may rely
on it unguarded on every conforming host (RATIONALE.md).

This is a **maximum, not a suggestion.** A host that exposes more accumulates carts
that run nowhere else, which breaks the format for everyone. Conformance tests it.

### 4.2 Numbers

Lua is built with **`LUA_32BITS`**: integers are 32-bit and wrap at ±2,147,483,647;
floats are 32-bit and carry about 7 significant digits. (Why that, and not doubles:
`RATIONALE.md`, "Numbers — 32-bit".)

A cart must not depend on more precision than that. A host built with 64-bit doubles
still conforms — it is strictly more precise — but a suite scene that carries float
arithmetic must be judged against the 32-bit player rather than a 64-bit build, which
would drift from it in the last digits (§11).

**An integral float prints without a fraction.** `tostring(3.0)`, `3.0 .. ""` and
`print(6 / 2)` all give `3`, where stock Lua 5.4 gives `3.0`. A cart mixes the two
kinds constantly — `flr` returns an integer, `/` a float — so the suffix is a wart
in a score display and a silent mismatch in a table keyed by `x .. "," .. y`. It is
one line in the VM's number formatter (`lobject.c`, `tostringbuff`), and a host that
builds its own Lua carries it. `math.type` still tells the two apart; only their
spelling agrees.

### 4.3 Errors

A Lua error terminates the cart. The host reports it to the user with the script line
number and returns to wherever the cart was launched from. A host MUST NOT leave a
crashed cart running or silently swallow the error.

---

## 5. Tick

A cart's logic runs at its **declared rate**: **30 Hz**, or 60 Hz when its manifest
says `"fps": 60`. The host calls `_update(dt)` once per tick at that rate and never
reduces it — a cart that counts frames plays at the wrong speed the moment the rate
moves, so a slower tick is a slower game, not a degraded one. `dt` is the tick
period (1/30 or 1/60), so movement written as `speed * dt` is correct at either
rate.

A host that falls behind catches up by running extra ticks in one frame, but only
while a tick costs under half the period — PICO-8's own line for running two ticks
per draw. Past that line a late frame slows time rather than snowballing, and debt
beyond one period is written off. A host reports that; it does not hide it by
lowering the rate.

A cart whose logic is entirely `dt`-scaled MAY declare `"fps": "free"`: the host
then does not pace it at all — `_update(dt)` and `_draw()` run once per host
frame, `dt` is the real elapsed time (a host MUST clamp it, so a stall slows the
cart's time rather than jumping it), and the draw rate is whatever the host can
sustain. A cart that counts frames MUST NOT declare it; the tick guarantees above
are exactly what such a cart needs, and `"free"` gives them up.

`_draw()` is called after `_update(dt)`, and never before the first `_update` has
run. A host under load MAY draw on an integer divisor of the tick — every second
tick, every third — while continuing to call `_update(dt)` at the full rate: logic
stays real-time and motion coarsens evenly. This is the only sanctioned form of
degradation; drawing three ticks in four is uneven delivery and is not it. A 60 fps
cart on a host that can draw 30 therefore runs two ticks per draw, which is
PICO-8's own degraded mode.

---

## 6. Drawing

All coordinates are canvas pixels, all colors palette indices. Every verb clips to the
canvas and honours the current `camera`, `clip` and `pal` state; the **shape** verbs
(`line`, `rect`, `rectb`, `circ`, `circb`, `oval`, `ovalb`, `tri`, `trib`) also honour
the fill pattern `fillp`.

| verb | effect |
|---|---|
| `cls(c)` | clear the screen to color `c` (default 0) |
| `background(c)` | declare a backdrop repainted before every `_draw` — `cls` you say once |
| `view(w, h)` | declare a logical viewport smaller than the canvas |
| `pix(x, y, c)` · `pix(x, y)` | set one pixel · with two arguments, **read** one: the index at `x, y`, camera-relative like the write, `0` off the canvas |
| `line(x0, y0, x1, y1, c)` | line |
| `rect(x, y, w, h, c)` | **filled** rectangle |
| `rectb(x, y, w, h, c)` | rectangle **outline** |
| `circ(cx, cy, r, c)` | **filled** circle |
| `circb(cx, cy, r, c)` | circle **outline** |
| `oval(x, y, w, h, c)` | **filled** ellipse inscribed in the `w × h` box at `x, y` |
| `ovalb(x, y, w, h, c)` | ellipse **outline** — the rim of the same fill, pixel for pixel |
| `tri(x1, y1, x2, y2, x3, y3, c)` | **filled** triangle — see §6.1 |
| `trib(x1, y1, x2, y2, x3, y3, c)` | triangle **outline** — see §6.1 |
| `tline(x0, y0, x1, y1, u, v, du, dv, ck)` | textured line sampled from the map — see §6.1 |
| `print(s, x, y, c)` | text, 8 × 8 fixed font |
| `camera(x, y)` | offset subsequent draws by `-x, -y`. No args resets. **Returns the previous offset** as two values, so `local px, py = camera(x, y)` … `camera(px, py)` saves and restores |
| `clip(x, y, w, h)` | clip subsequent draws to a rect. No args resets |
| `pal(c0, c1)` · `pal(c0, c1, 1)` | draw color `c0` as `c1` · with a third argument of `1`, **show** `c0` as `c1`: the screen palette, composed after the first. No args resets both |
| `palt(c, on)` | mark index `c` transparent. No args resets |
| `fillp(p, c)` | a 4 × 4 fill pattern for the shape verbs: a set bit is a hole, a hole takes colour `c` or is left alone when `c` is absent or negative. No args resets to solid |

`pal(c0, c1)` is the **draw palette** — it remaps colors as they are written to the
canvas, and a pixel already there does not move. `pal(c0, c1, 1)` is the **screen
palette**: a second remap **composed after** the first, so a pixel written as `c0`
lands as `spal[pal[c0]]`. It applies as pixels are drawn, like the first — **not** to
pixels already on the canvas — so a whole-frame recolour is set *before* the frame's
`cls`, and a fade redraws each frame under that frame's table. The two exist separately
because they compose: `pal(2, 8)` with `pal(8, 11, 1)` draws a 2 as 11 *and* a real 8
as 11, which one table cannot say — and it is the shape every PICO-8 fade and secret
colour already has. Both reset with `pal()`, and both reset at the start of every frame
like all draw state. A layer's pixels are copied as they are; the third argument does
nothing on a layer. (§12.1 records why it composes rather than applying at flush.)

**`fillp(p, c)`** is the dither. `p` is sixteen bits read as a 4 × 4 cell, row by
row from the top-left, bit 15 first; a **set bit is a hole**. The cell is anchored to
the **screen** — pixel `(x, y)` after the camera is a hole when bit
`15 − 4·(y mod 4) − (x mod 4)` is set — so a scrolling world does not crawl its
dither, and `clip` does not shift its phase. A hole pixel takes `c` (through `pal`,
like any colour) when `c` is given and not negative, and is **left untouched**
otherwise, which is how a shape fades over what is already there. It applies to the
nine shape verbs and to nothing else: `pix` is the cart's own per-pixel statement,
`print`, sprites and the map carry their own pixels, and `cls` is a reset. Bits above
15 are ignored; `0` is solid. Like every other piece of draw state it resets at the
start of each frame.

`oval` and `ovalb` are one walk (an integer midpoint ellipse, no division, no
float, so every host performs identical arithmetic): the fill is the rows between the
outline's extremes, so `ovalb` drawn over `oval` rings it exactly. A `w` or `h` of
zero or less draws nothing; `1 × 1` is a single pixel.

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

### 6.1 The 3D verbs

> **Core as of 0.3.** `tri`, `trib`, `sspr` and `tline` are implemented in every
> reference implementation, have native kernels in the reference console, and
> are golden-checked by counted scenes of their own. They were provisional through 0.2
> and were promoted by the gates recorded at the end of this section, on
> evidence rather than argument. The batch verbs that used to fill this section
> are **deleted**, and the measurements that deleted them are recorded below so
> they are not reinvented.

> They are grouped here rather than scattered through §6 and §7.1 because they
> share a membership rule and a cost profile a cart author should read together
> before leaning on any of them. The tables in §6 and §7.1 are still where each
> one's signature lives.

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
| Mode 7 plane | ~120 `tline` calls | **~8 ms for a half-screen plane, measured on the FASTER reference board** (~210 ns/texel). The first kernel measured ~25 ms — two 64-bit software modulos per texel — and this row is what caught it; the fix (reduce once, wrap by conditional subtract) moved no pixel, which the golden proves. Floor board (2026-08 bench): 100 full-width lines cost ~14 ms over the ~18 ms baseline frame, ~440 ns/texel — a half-screen plane ≈ 17 ms, at the 30 Hz edge beside the baseline compose; third-screen planes are comfortable |
| raycaster | script DDA + `sspr`/`rect` columns | measured on glass: ~32 fps full-res, past 60 at half-res |
| flat-shaded polygons | `tri` per face | dispatch + fill, small triangles near the call floor |
| scaled sprites, billboards | `sspr` | sub-ms each |

These are **call-bounded**: cost scales with verbs issued, and the host owns
every pixel. What the set does not cover is **step-bounded** work whose output is
data-dependent per sample — voxel-terrain rendering (Comanche), general textured
3D, per-pixel effects. No verb fixes those: the cost is the cart's own
interpreted loop. They belong to a vendor extension (§10) or to a compiled cart
(§16), and a cart author should know that *before* building — which is
what this table is for.

**The gates they cleared**, kept because they are the bar the next candidate
verb has to clear too:

1. **A native kernel in the reference console.** The floor board runs the
   interpreted fallbacks at 7.5 ms per `tri` and 36 ms per small `sspr` — a verb
   slower than the frame it draws into cannot honestly be specced. All four have
   C kernels in `libmoy/`, and the reference console grew native `tri`, `sspr`
   and `tline` kernels in its 2026-08 build.
2. **Golden frames in the counted set.** The `provisional` and
   `provisional_tline` scenes were reported but excluded through 0.2; 0.3 counts
   them, so a host that skips these verbs now fails conformance rather than
   passing with a gap. §6's `fillp` scene already drew with `tri` and `trib`,
   which is what made the exclusion untenable.
3. **A measured row in the reference bench on every reference board**, so the
   first cart author to lean on one reads a cost, not a hope.

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
  a verb is a vendor extension (§10) or a library inside a compiled cart (§16),
  never core. Core verbs are the primitives every genre shares.

---

### `layers`

Off-screen buffers for scrolling worlds — draw a wide level once and window-copy it
each frame instead of re-rendering it.

| verb | |
|---|---|
| `make_layer(w, h)` | a layer speaking the full drawing API, with its own camera, clip, pal and palt — or **nil** if the host declines |
| `draw_layer(layer, cx, cy)` | blit the screen-sized window whose top-left is `(cx, cy)`, clamped into the layer as below; like `cls`, this composites and so ignores the screen's camera, clip and pal |

`draw_layer` clamps its camera on each axis into `[0, max(0, layer − screen)]`, so
the window never leaves the layer: on an axis where the layer is smaller than the
screen the camera is 0, and the screen past the layer's edge keeps what it held.

§1.1 reserves one full-screen layer, so `make_layer` succeeds at least once on every
conforming host. Beyond that a host may decline and return nil, which a cart handles
the way it handles any allocation that can fail — by testing, not by guarding a verb.
A layer's own draw state is its own: setting `camera` on a layer does not move the
screen's.

### `background` and `view`

Both are **core verbs whose effect depends on the host**, in the same way
`touch()` reads nil where there is no pointer and `textmode` is a no-op on a
keyboard with one mode. A cart calls them plainly; what varies is how much a
given console can do with them, never whether the call works.

`background(c)` declares a backdrop instead of clearing to it every frame — the
same pixels as a `cls(c)` at the top of `_draw`, said once. A console that can
do better than a flat clear (restoring a cached backdrop, blitting a prepared
layer) does; one that cannot clears. The cart cannot tell, and should not need
to.

`view(w, h)` declares that the cart only uses a centered `w × h` region of the
canvas. A console with a bigger screen composites that region at the largest
integer scale that fits, which is how a converted 128 × 128 cart fills a display
instead of sitting in a letterbox; a console that presents pixel-for-pixel draws
it unscaled, which is what it would have done anyway. Declaring `"canvas"`
(§3.1) is the static twin — the raster itself shrinks and `W`/`H` change with it
— where `view` chooses the region at runtime with the full canvas still
underneath.

Neither can mislead a cart, which is why neither is an extension and neither
needs a `~= nil` guard.

## 7. Sprites, map, input

### 7.1 Sprites

| verb | effect |
|---|---|
| `spr(n, x, y, colorkey, scale, flip)` | draw sheet tile `n` at `x, y` |
| `sspr(sx, sy, sw, sh, dx, dy, dw, dh, colorkey, flip)` | stretch a sheet **pixel** region to `dw × dh` at `dx, dy` — see §6.1 |
| `sget(x, y)` | the index at sheet **pixel** `x, y`; `0` off the sheet |
| `sset(x, y, c)` | write a sheet pixel; `c` is masked to 0–15 (§2.3), a write off the sheet is dropped |
| `fget(n)` · `fget(n, b)` | tile `n`'s flag byte (§3.5) · whether bit `b` (0–7) of it is set; `0` / `false` off the sheet |
| `fset(n, v)` · `fset(n, b, on)` | write tile `n`'s flag byte · set or clear one bit of it |

`n` is a sheet tile, **0–511**. `colorkey` is the transparent palette index, `-1` for
opaque (default). `scale` is an integer enlargement, default 1. `flip`: `0` none, `1`
horizontal, `2` vertical, `3` both. A sprite larger than one tile is drawn as its
tiles — adjacent `spr` calls.

`sspr` addresses the sheet in **pixels, not tiles**, and its scale is arbitrary rather
than integer.

`sget` and `sset` make the sheet readable and writable at runtime — generated art,
art as data, a texture baked from the screen. What `sset` writes is what the next
`spr`, `sspr`, `map` or `tline` of that tile draws; a host that caches tiles owes
exactly that. The sheet outlives a frame — nothing resets it — so a cart that edits
it and wants its art back must write it back.

**Drawing sprites needs only `spr`.** Many tiles is a plain loop over it — a
conforming host makes that loop cheap (§6.1's batching note), and the batch verb
this section once pointed at is deleted for exactly that reason.

### 7.2 Map

| verb | effect |
|---|---|
| `map(mx, my, w, h, sx, sy, colorkey, scale, layers)` | blit a `w × h` region of the tilemap at cell `mx, my` to screen `sx, sy`; with `layers` non-zero, only the cells whose tile's flags (§3.5) share a bit with it |
| `mget(x, y)` | tile id at a cell; `-1` for empty or out of range |
| `mset(x, y, tile)` | write a cell; a negative id clears it |

`layers` is how a level is drawn in strata — the ground with mask `1`, the
foreground with mask `2` after the sprites — from one map and one call each. It is
a filter on the **tile's** flags, not the cell's, so tagging a tile once tags every
cell that uses it; `0` (or absent) is no filter at all. A cart with no `flags.moyflags`
has all-zero flags, so a non-zero mask draws nothing there, and `fset` at runtime
changes what the next `map` draws.

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
| `btnp(name, player)` | true on the tick it was pressed (released → held edge) |
| `players()` | how many controllers are connected. **Always ≥ 1** |

`btnp` fires **once per physical press, with no autorepeat** (§12.2). A cart wanting
repeat implements its own timer. The edge is per **tick** (§5): a press that lands
between two ticks is held until the next tick takes it, and a second tick run in
the same host frame does not see it again — one press is one edge at any pair of
host and cart rates, and the edge stays visible through that tick's `_draw()`.

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

An SFX may also carry an optional `"filters"` (default 0), **one byte holding
five independent settings**, in PICO-8's own packing — the same
carried-verbatim policy as a step's effect nibble:

| field | read as | values |
|---|---|---|
| `noiz` | `f & 2` | shapes the NOISE instrument with a sawtooth; no effect on the other seven |
| `buzz` | `f & 4` | selects each instrument's harsher twin — a different waveform, not a post-effect. Noise has no twin and ignores it |
| `detune` | `(f / 8) % 3` | 1 or 2: a second oscillator beside the note at a per-instrument ratio, mixed at half. Noise is exempt |
| `reverb` | `(f / 24) % 3` | 1 or 2: a delay line fed back at half — 16.6 ms or 33.2 ms |
| `dampen` | `(f / 72) % 3` | 1 or 2: a high shelf, −6 dB above 2400 Hz or −12 dB above 1000 Hz |

`noiz`, `buzz` and `detune` change the OSCILLATOR and so apply per note;
`reverb` and `dampen` are per-CHANNEL post-processing and keep sounding after
the note that started them has ended. `0` is the dry sound every SFX written
before this had, so the field is additive and absent means unchanged.

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
| `srand(seed)` | seed `rnd`: the same seed replays the same sequence **on the same host** |
| `flr(x)` | floor to integer |
| `quit()` | end this cart; the host returns to wherever it was launched from |
| `W`, `H` | canvas dimensions — read these, do not assume 320 × 240 |

`quit()` does not replace the host-owned exit (§7.3) — the player can always leave
a cart without it. It exists so a cart can end *itself* (a menu's EXIT entry, a
game-over screen), and it is the required exit for a `textmode(true)` cart.

`srand` is what makes a cart's randomness reproducible — replays, a daily-seed
puzzle, a bug report that says "seed 42". It pins the sequence **per host**, not
across hosts: this spec defines `rnd`'s range and not its generator, so two
conforming hosts may still disagree on every number, and a conformance scene
still may not call either (§11). `seed` is taken as an integer; the same seed
on the same host is the same sequence, every time.

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
opportunistically — check the verb exists before calling it (`if espnow ~= nil
then ... end`) and declare nothing. Such a cart runs on every host,
degraded where the extension is absent, lit up where it isn't; an extension's
verbs do not exist as globals on a host without it.

**What belongs here, and what does not.** An extension is for a capability whose
absence a cart cannot be shielded from *and* which a conforming host may
genuinely lack — a radio, a second cart language, an on-device authoring format.
Hardware, in other words, rather than software a host could always choose to
implement.

`background` and `view` do not qualify, and neither does `layers`: the first two
because a console that cannot honour them does something truthful anyway, and
layers because §1.1's floor now covers one. **A verb whose absence can be
degraded truthfully, or afforded by every conforming host, belongs in core;
only one whose absence cannot belongs here.** Deciding which is which is the
extension designer's real work, and getting it wrong in the generous direction
is worse than in the strict one — a cart that silently draws nothing is harder
to diagnose than one a host refused by name.

**There are currently no standard extensions.** Both that this section once defined
turned out not to need it: `background` and `view` because a host that cannot honour
them does something truthful anyway (§6), and `layers` because measurement put it
inside the floor (§1.1). That is the section working as intended rather than emptying
out — an extension is for a capability whose absence a cart cannot be shielded from,
and each of those failed that test on inspection.

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

(`layers` used to be a standard extension here. It is core now — see §6 — because
measurement put a full-screen layer inside the 400 KB floor, so requiring hosts to
negotiate it was buying nothing.)

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
**pixel-identical** output. The output is the canvas — one palette index per pixel —
which, because both palettes compose as pixels are drawn (§6), is also the frame as
shown: what a host flushes and what a golden is.

The suite is a set of carts, each exercising one area — primitives, sprite flips and
scales, clip and camera interaction, palette remaps, text, map blits, layer windows,
input edges — plus golden frames. A runner diffs your output frame by frame.

**The golden frames are rendered by `moycore`**, the Python raster the suite ships
with, and every scene is a recorded verb trace of integer arguments — so no float
enters the goldens as they stand.

**The WebAssembly player** (`runner/`) is the **tiebreaker** for any disagreement
between this document and observed behaviour, and it agrees with the goldens on every
scene. Where the spec text and the player conflict, **the spec text is wrong and gets
fixed** — but implementations are tested against the player. The player holds that
role precisely because it is the build that follows §4.2: its Lua is compiled
`LUA_32BITS`, like the hardware consoles. A host may render the suite through any
tooling it likes, but frames captured from a 64-bit-Lua build are not golden — the
moment a scene carries float arithmetic, that build will drift in the last digits
(§4.2), and any scene that does must be captured from the player.

The §4.1 sandbox ceiling is a conformance requirement — a cart that reaches `io` must
fail on every conforming host — but **the suite does not currently test it**: it asks a
player for frames, and refusing a cart produces none. Until the runner grows a
must-fail check, that ceiling is verified per implementation (in this repository, by a
CI job over the C core) and taken on trust elsewhere. Audio is excluded (§8.3). The
§6.1 verbs are counted like any other since 0.3, in the `provisional` and
`provisional_tline` scenes that keep their names.

---

## 12. Decisions worth arguing with

Everything in this spec is decided. These are the ones where a reasonable person would
decide differently. Each entry states the decision and what it costs; where the
argument runs longer than that, it lives in `RATIONALE.md` under the heading named
here — and **only** there. A decision argued in two documents is a decision that will
eventually be argued *differently* in two documents.

### 12.1 — The screen palette, reversed — then composed.

PICO-8 has two palettes: a draw-time remap, and a screen palette applied at flush.
This spec once had only the first, on the argument that the second "doubles the
palette state every primitive must consult". That argument was wrong — a second
table is consulted by no primitive — and the verb was added, as PICO-8 has it: a
pass over the finished frame. That was wrong too, for the reason the first argument
missed. On an indexed canvas the pass is a byte lookup. On a direct-colour canvas
(§1.1's RGB565 option) it is a **reverse** lookup — which index was this word? — and
measured on the reference console's three boards it cost roughly **half a frame**
(moybyte #218: 8.3–10.9 ms, on hosts running 42–62 fps), with locality and the
hash both ruled out as the cause. A verb the reference console cannot afford is not
in the spec, so the screen palette now **composes**: `store[i] = wire[spal[pal[i]]]`,
rebuilt per call, and a pixel costs one lookup whether a cart set neither palette
or both. **Cost:** a pixel already on the canvas does not move. A fade over a frame
that is not redrawn, and a remap issued after drawing within a frame, behave as the
draw palette would. Of the sixteen carts in the PICO-8 conformance corpus, six hold
a screen palette, and every one sets it before it draws — the machine restores it
from `0x5f10` at the top of each frame, ahead of any cart code — so the idiom the
verb exists for is unchanged.

### 12.2 — `btnp` has no autorepeat.

PICO-8 repeats a held button after ~15 frames at
~4-frame intervals. This spec fires once per press. Autorepeat in the console means
every host must match the rate exactly or menus feel different everywhere; a cart that
wants it can write four lines. **Cost:** converted PICO-8 carts relying on repeat for
menu navigation feel wrong until the converter injects a shim.

### 12.3 — Sprites are 16 colors, primitives are 64.

Format compatibility with PICO-8's sheet, bought at the price of the sixteen (§2.3);
cart-supplied palettes (§2.2) make it *sixteen at a time* rather than sixteen specific
colors. **Cost:** an artist cannot use more than 16 distinct colors within one sprite
sheet, only in backgrounds and shapes. — *RATIONALE, "Sprites — 16 colors".*

### 12.4 — 400 KB is the memory floor, and layers fit inside it.

Now **measured** rather than derived (§1.1): a deliberately heap-heavy cart with a
full-screen layer totals 295 KB on the reference implementation, so the layer that
used to be an optional extension sits comfortably under the floor and is core (§6).
Any kind of RAM counts, so the floor only bites SRAM-only parts. **Cost:** it rules
those out below 400 KB — including RP2040-class boards at 264 KB, which were already
excluded before layers moved and are not newly so. A lower floor would mean a smaller
screen, sheet or heap promise, and those are worse trades. **What would reopen it:**
a cart class that genuinely needs several layers at once, since only one is
guaranteed. — *RATIONALE, "Memory — 400 KB".*

### 12.5 — 512 tiles, but only 254 placeable on a map.

Keeping map cells at one byte (storing `tile_id + 1`, so a zeroed map is blank) is
worth more than a uniform addressing range. **Cost:** a boundary an author has to
learn — `spr` reaches tiles the map editor can't place. — *RATIONALE, "Sheet — 512
tiles" and "Tilemap — one byte per cell".*

### 12.6 — No direct framebuffer access.

TIC-80 exposes raw VRAM, which makes any
effect possible and makes the pixel format part of the cart contract — a cart then
writes to *that* framebuffer rather than *a* framebuffer, and hosts lose the freedom to
render at a different depth, scale or byte order. This spec keeps the canvas opaque and
covers the cases raw access was wanted for with shaped verbs instead (§6.1).
**Cost:** effects whose *logic* is genuinely per-pixel — plasma, fire, tunnels — cannot
be written as Lua carts. That is the deliberate boundary, and it is a statement about
*this* binding: the compiled-cart binding is where that boundary moves (§16.5), with
a framebuffer in the cart's own linear memory rather than raw access to the host's.

### 12.7 — Cover art is deferred, and the icon is a pointer.

PICO-8's `__label__` is tempting to copy and answers a different problem: it exists
because a PICO-8 cart **is** a PNG, so the label is the picture of the thing you
distribute. A moy cart is a folder, and the medium that forced the feature isn't
there.

Under the one word "thumbnail" are two requirements with opposite costs. An **icon**
must exist for every cart or lists have holes in them, and §3.4 buys that for one
optional manifest field. A **cover** is promotional, optional, and only pays for
itself once there is a catalogue to browse — while every way to spec one today is a
bad trade: hex nibbles are 16 colors and uncompressed (a full-screen image is 75 KB of
text against §12.4's floor), indexed-plus-RLE makes every implementer write a second
codec, and PNG puts a zlib decoder on a microcontroller in a format whose data files
are otherwise all readable text. §14 moves this document to a neutral home once a
second implementation passes conformance, and an image format is exactly what should
be settled *with* that implementer instead of guessed at alone. Until then it is an
extension.

**Ruled out permanently:** a host-captured screenshot as a format feature. A host can
already run a cart and cache a frame, so it needs no spec — and it is the wrong
artefact, because an automatic frame is arbitrary and the author should choose how
their game is represented.

**Cost:** a store built on 0.3 lays out 8 × 8 tile art and will look sparse beside a
storefront with key art. Right way round: a missing cover is a design problem later, a
wrong image format is a compatibility problem forever.

### 12.8 — Several files, several chunks — not one program pasted together.

`sources` (§4) runs each script separately, so a `local` in one is invisible to the
next. PICO-8's `#include` does the opposite: it splices the text in, making one
program with one scope, and that is what most people expect because it is what they
have used.

Splicing was rejected on two costs, both paid by the reader rather than the author.
A spliced program has **one** line numbering, so a syntax error in the first file is
reported at a line in the third — and a crash at "line 1413" of a cart whose own code
begins at line 1 is a debugging session spent finding the offset. Separate chunks
name the file and count from its own first line. Second, the splice has to exist: the
host holds the joined program beside the pieces it joined, double the cart's code at
the moment of loading, on the host with the least memory to spare.

**Cost:** a prologue cannot hand the cart a private helper. Everything shared is a
global — one flat namespace, and a table lookup per call rather than an upvalue slot.
The first is a discipline a program this size already lives with, since the console's
own verbs are globals too. The second is real, and its answer is an alias at the top
of the file that uses the name (`local spr = spr`): a line a person can read and a
converter can write.

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

## 15. Bindings

The verb table above is the contract; Lua is the **first binding of it**, not its
definition. A binding is the language a cart's `main` is written in, and the
manifest's `"runtime"` names it (§3.1): absent or `"lua"` is §4, `"wasm"` is §16.
What a host owes a binding it does not implement is settled in §3.1: a clean
refusal, never an attempt to run the file anyway.

**Lua is core; the WebAssembly binding is optional.** Every conforming host runs
Lua carts. A host that implements §16 runs a compiled cart exactly as §16 says, and
one that does not refuses it by name. A compiled cart therefore runs on every
console that took the binding on and nowhere else — the trade an extension makes
(§10), without a vendor namespace, because the binding is defined here rather than
by one console.

The second binding exists for the work the first cannot hold: **step-bounded**
rendering (§6.1) — voxel terrain, general textured 3D, per-pixel effects,
emulators — where the cost is the cart's own loop and no verb can absorb it.
WebAssembly is the one compilation target every systems language shares, one
artifact runs on every tier including the browser, and it is sandboxed by
construction: linear memory is bounded and imports are the only capability
surface, so the verb table literally is the sandbox. It is settled on
measurements rather than on taste — on reference hardware an interpreted WASM
runtime does not pay for itself and an AOT-compiled one pays many times over
(RATIONALE.md, "The WebAssembly binding").

One consequence reaches back into this document. A compiled cart brings its own
rasterizer and needs the one thing the verb table cannot give it: a framebuffer in
**the cart's own linear memory**, handed over once per frame (§16.5). Reaching
pixels through a per-pixel import instead pays a language-boundary crossing 76,800
times a frame and is dead at any VM speed. §12.6 declines to give a *Lua* cart a
framebuffer; §16 is where that boundary moves, and it never exposes the **host's**.

A Lua cart gets nothing from §16, deliberately: there is no path from Lua into the
compiled tier, and a Lua cart that outgrows its budget is ported, keeping its verbs,
its tick and its assets (RATIONALE.md says why).

## 16. The WebAssembly binding

A cart whose manifest says `"runtime": "wasm"` is a **compiled cart**: its `main`
is a WebAssembly module, and this section is the contract it and a host meet at.
Three executable copies of the contract sit beside it, each tested against the
others:

- **`wasm-imports.json`** — the import table as data, one row per import: its wasm
  type, its WAMR signature string, the section of its verb, and the notes that say
  how the verb's Lua forms become one wasm function.
- **`libmoy/include/moy_cart.h`** — the same table as the C declarations a C or C++
  cart includes.
- **`libmoy/src/moy_wasm.c`** — the host's side of the table in C, over WAMR or
  under a JavaScript embedder's own engine (libmoy's README says how).

`moy check` holds a compiled cart's module to this section, its manifest and the
table.

### 16.1 The cart

```json
{ "format": "moy-1", "title": "…", "runtime": "wasm", "main": "main.wasm",
  "memory": 64 }
```

`main` names the module, and for this runtime it defaults to `main.wasm`.
`memory` is required: the cart's linear memory in 64 KiB pages (§16.7).
`sources` does not apply — a compiled cart is one module — and a manifest that
lists it is refused the way §4 refuses a broken one. Every other field keeps its
§3.1 meaning, `canvas` and `fps` included, and every asset file is unchanged:
`sprites.moygfx`, `map.moymap`, `flags.moyflags`, `sounds.json`, `config.json`.
**The `.wasm` is the sole portable artifact.** How a host executes it is the
host's own business (PORTING.md): a host may keep a compiled form of the module
beside it — the reference console does, one per chip — but no other host reads
one, and a cart is complete without it.

Source is welcome beside the module — `src/` in the folder, or a `"source"`
manifest field carrying a URL — and never required or verified. The
always-readable tier is the Lua cart.

### 16.2 Module shape

- **Profile: wasm32 — the MVP, and three additions every engine that runs it
  has:** an exported mutable global (`__stack_pointer`, §16.10), the
  sign-extension operators, and the non-trapping float-to-int conversions. No WASI,
  no threads, no SIMD, no bulk memory, no reference types, no GC proposal. The
  profile is pinned so a 2026 toolchain and a 2030 one produce carts the same host
  runs; extensions to it are a spec revision, not a toolchain default. A cart uses
  more than one core through `par` (§16.10), never through threads.
- **One linear memory, the module's own**, exported as `memory`, its minimum equal
  to its maximum equal to the manifest's `memory`. Not imported, not shared, not
  64-bit.
- **Exports:** `_init()`, `_update(f32 dt)`, `_draw()` and `memory` — all four
  required, at exactly those types; an empty hook is an empty function. The host
  calls the three hooks as the §5 tick calls the Lua ones, with `dt` the tick
  period. A cart that imports `par` also exports `_par(i32 i, i32 arg)` and its
  stack pointer, the mutable `i32` global `__stack_pointer` (§16.10); a `_par` or a
  `__stack_pointer` at another type is refused whether or not it does. Any other
  export is ignored.
- **No start function.** Nothing in the module runs before `_init`.
- **Imports: functions from module `"moy"`, each a row of the import table at that
  row's exact type.** A cart imports only the rows it uses. The Lua build is
  `LUA_32BITS` (§4.2), so the two bindings already share a numeric world; nothing
  widens.
- **No other imports exist.** That sentence is the entire §4.1 sandbox for this
  binding. A module that imports anything else — from another module, a memory, a
  global, a table, a name outside the table, a row at the wrong type — is refused
  before it runs.

Any toolchain that emits that profile makes a cart, and none needs an SDK. For C
and C++, `moy_cart.h` declares every import; with clang it is one command (the two
memory sizes are `"memory": 64` in bytes):

```sh
clang --target=wasm32 -O2 -nostdlib -Wl,--no-entry \
      -Wl,--export=_init,--export=_update,--export=_draw \
      -Wl,--initial-memory=4194304,--max-memory=4194304 \
      -o main.wasm main.c
```

`zig build-exe -target wasm32-freestanding` and Rust's `wasm32-unknown-unknown`
produce the same shape.

### 16.3 The import table

**The import table is the verb table.** Every verb the Lua binding installs is one
import of the same name and the same §6–§9 meaning, and six exist because this
binding needs them: `blit` and `blit565` (the framebuffer, §16.5), `read` (the
cart's own files, §16.6), `target` (drawing into a layer, §16.4), `snd` (the
sample stream, §16.9) and `par` (the cart's own work across the cores, §16.10).
`wasm-imports.json` lists every one; a verb the spec gains is a row there before it
is anything else.

`W` and `H` are not imports. The canvas is the manifest's (§1, §3.1) and a host
runs the cart at exactly that size or refuses it, so a compiled cart knows both
when it is compiled.

### 16.4 Marshalling — one Lua verb, one wasm function

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
- **Several results** are written as consecutive `i32` at an out pointer passed as
  the last argument, which may be 0 to discard them (`camera`'s previous offset,
  `touch`'s four values).
- **nil is a value the verb could not otherwise return**: 0 for a layer handle and
  for `touch` with no pointer, -1 for an absent `cfg` key. A verb that already
  answers an integer for "nothing" keeps it (`mget`'s -1).
- **Strings are bytes in linear memory, passed as a pointer and a length** — no
  terminator and no encoding, exactly the byte string a Lua string is (§6's
  `print`). A name drawn from a closed set is its index in the order the spec lists
  the set instead: `btn(0, p)` is `btn("left", p)`. A verb that answers a string
  copies it into a buffer the cart supplies and returns its whole length, so a
  short buffer is visible (`cfg`).
- **Layers are handles.** `make_layer` returns a positive `i32` that names the
  layer until the cart ends, or 0 where Lua returns nil. Where a Lua cart calls a
  method, `ly:rect(…)`, a compiled cart points the drawing verbs at the layer —
  `target(ly)` — draws, and points them back with `target(0)`. The verbs `target`
  redirects are exactly the ones a Lua layer answers, a layer keeps its own draw
  state as it does in Lua, and the target is the screen whenever the host calls an
  export. A handle `make_layer` never returned is a trap, as a method call on
  something that is not a layer is an error in Lua. Nothing frees a layer: it lives
  until the cart ends, where Lua's collector may end it sooner.
- **Pointers are offsets into linear memory**, checked on every call; a range that
  leaves the memory is a trap. 0 means "none" wherever a pointer is optional, since
  no toolchain places an object at address 0.
- **`time()` is the clock.** There is no clock import: §9's `time()` answers
  milliseconds since the cart started, which is all a cart needs to measure. It
  paces itself by returning from `_update`, and §5 calls it again.
- **No import blocks.** Every import completes in time bounded by its arguments —
  `read` by its length, `blit` by the frame, `snd` by its count, `par` by the
  cart's own items — and none waits for input, a timer, the display, the audio
  output or the network. There is no sleep and no vsync wait: a cart waits by
  returning.
- **`quit()` does not return.** The host unwinds the cart as it would for a trap
  and treats the unwinding as the cart ending itself (§9), with no report.

### 16.5 The framebuffer — `blit` and `blit565`

A compiled cart reaching pixels through the `pix` import would pay a crossing per
pixel, 76,800 a frame. So it hands over a whole frame at once:

```c
void blit(i32 frame, i32 pal);   /* frame: W x H bytes in linear memory, one
                                    palette index per pixel, row-major.
                                    pal: 0 for the cart's own palette, or 768
                                    bytes of RGB -- a 256-entry palette
                                    presented with THIS frame */
```

`W × H` is the declared canvas (§1), 76,800 bytes at the default 320 × 240. With
`pal` 0 an index names the cart's §2.2 palette entry, modulo 64; otherwise it names
one of the 256 entries at `pal`. The frame covers the whole screen and ignores the
draw state — camera, clip, both palettes, `palt`, `fillp` — and the target: like
`cls` it composites rather than draws. It is legal only inside `_draw`, at most
once per `_draw` counting `blit565`; a call anywhere else, or a second one, is a
trap. A cart may freely mix `blit` with ordinary verbs; draw order is call order,
so a HUD drawn after the blit lands on top of it.

**The frame stays as blitted until `_draw` returns.** A host may present it
straight from the cart's memory — a panel flush that resolves the palette as it
ships the frame, say — and so read it after the call rather than during it. A cart
therefore leaves the frame it handed over, and its palette, unchanged for the rest
of that `_draw`; from its next hook the memory is its own again. What the cart
draws is the same either way: a verb drawn over the frame, or a pixel read from it,
meets the frame as it was blitted.

A frame a palette blit wrote holds up to 256 colours, which the 64 indices of an
indexed canvas cannot represent, so a host running this binding keeps the screen in
direct colour while a compiled cart runs — the choice §1.1 already allows. What
`pix` reads back from a pixel a palette blit wrote is host-dependent (an index
0–63), and no conformance scene reads one.

**The per-frame palette does not reopen §12.1.** That decision forbids
retroactively re-meaning pixels already drawn on a retained canvas; a `blit` is a
complete frame delivered together with its own palette — nothing is retained,
nothing re-meant, and the host's cost is rebuilding a 256-entry table per frame,
which is noise. It buys the runtime-palette work the fixed §2.2 table cannot
express: fades and flashes, palette cycling, and the emulators and ports whose
palette changes at runtime or brings more than 64 entries of its own. Per-scanline
palettes remain a bridge deliberately not crossed.

Nor does it reopen §12.6: the cart writes *its own* memory, the host's framebuffer
stays opaque, and hosts keep every freedom of depth, scale and byte order. Assets
stay host-side as well: `spr`, `map` and `sspr` render the cart's sheet and map as
ever, and a cart that wants its files' bytes reads them (§16.6).

```c
void blit565(i32 frame);   /* frame: W x H RGB565 words in linear memory,
                              LITTLE-ENDIAN, row-major -- 153,600 bytes at
                              320 x 240 */
```

`blit565` is the second submission format, alongside `blit` and never replacing
it, for content that was never palettized — gradients, shaded 3D, photographic art
— which `blit` would make the cart quantize or dither first. Exactly `blit`'s rules
apply: only inside `_draw`, at most once counting `blit`, the whole screen whatever
the draw state, and the result treated exactly as a §6-drawn frame, freely mixed
with ordinary verbs in call order.

**The byte order is fixed here, and is not "whatever the panel wants."** The
moment the submitted layout tracks the display, a cart writes to *that*
framebuffer rather than *a* framebuffer and §12.6 is quietly reopened. A host with
a byte-swapped 16-bit panel swaps; a browser expands to RGBA8888; a desktop player
expands to RGB888. Pinning the order also keeps this tier golden-checkable
(§16.11).

**A cart that could have been indexed should stay indexed.** Two bytes a pixel is
twice the store traffic of one, and a software rasterizer is store-bound: on the
reference console's boards `blit565` costs the cart more than it saves the host,
and on the floor board several times more (RATIONALE.md has the measurements). It
is for pixels that are direct-colour by nature, where the indexed route would cost
a quantization pass rather than save a store.

### 16.6 The cart's own files — `read`

```c
i32 read(i32 name, i32 name_len, i32 offset, i32 dst, i32 len);
```

Copies up to `len` bytes of the cart's own file `name`, starting at byte `offset`,
into linear memory at `dst`, and returns how many it copied. With `len` 0 it
copies nothing and returns how many bytes remain from `offset` — at offset 0, the
file's size.

`name` is a path relative to the cart's folder: bytes, `/`-separated, every
segment non-empty and neither `.` nor `..`, with no `\` and no NUL. A name that is
absent, or that breaks that rule, reads 0, and so does an offset at or past the end
— so a cart cannot tell a missing file from an empty one, and cannot reach
anything outside its folder. That is as far as §0's "no filesystem access"
stretches: the folder already is the cart. Every file in it is readable, the
manifest and the module included; nothing is writable, and `pmem` (§9) stays the
only state a cart keeps.

It exists because a ported engine needs its own data and the sprite sheet cannot
carry it — Doom reads a 4 MB WAD. The read is synchronous and bounded by `len`: a
host whose carts live on slow storage makes it slow, and never makes it wait on
anything else. A user's own files — a document the cart did not ship — are a
different capability and would be a different import, so this one never widens
past the cart's folder.

### 16.7 Memory — one fixed block, checked before it exists

A compiled cart's memory is one block, sized by its manifest and never grown.
`"memory": N` declares N pages of 64 KiB (65,536 bytes each), and it covers
everything the cart has: its data, its stack, its heap, any frame it blits from.
The module's memory minimum and maximum are both N, so `memory.grow` answers -1, as
wasm specifies, and a cart plans for that rather than trapping on it.

A host checks this **before it allocates anything.** A manifest without `memory`,
or a module whose memory disagrees with it, is refused — §3.1's clean refusal —
before the module is instantiated: never half-loaded, never grown to fit. So is a
cart whose whole load footprint — the declared memory, the module's code and the
engine's working pool — is more than the host can give it, and that refusal is a
plain notice to the player naming both figures, never an error report or a crash.

**§1.1's ≈ 400 KB does not apply to this binding.** It is the script tier's floor,
stated for a host that owns every pixel; a host implementing this binding already
carries a WebAssembly runtime and the memory a module and its linear memory load
into, and a `blit565` frame alone is 153,600 bytes. **This binding's floor is the
floor board's**: the reference implementation's smallest board's share of its
cart-runtime reserve with the runtime resident, so a compiled cart within it runs
on every board of that lineup — the no-fragmentation rule §1.1 enforces for
scripts. A cart above it is allowed: it runs only on consoles with more memory, and
a console that cannot fit it refuses it at launch with the notice above. Like
§1.1's floor it is checkable before any host sees the cart, and `moy check` reports
a manifest above it as a warning that names the floor, never a refusal. A host that
cannot give a cart within the floor its pages is short of the floor, and fixing
that is the host's problem, as §1.1 makes its own floor the implementer's. What the
floor bounds is the whole load footprint, not `"memory"` alone. The figure is not
yet measured (`proposals/wasm-runtime.md`, open item 8); until it is, `moy check`
carries it as a named constant with no value and warns about nothing on size.

### 16.8 Traps

A trap ends the cart the way a Lua error does (§4.3). Whatever makes wasm trap —
`unreachable`, an out-of-bounds access, an integer division by zero, a stack
overflow — traps the cart, and so does everything this section calls a trap: an
import handed a range outside linear memory, a layer handle `make_layer` never
returned, a `blit` outside `_draw` or a second one inside it, an import called from
one of `par`'s items, and `par` handed a negative count or stacks outside memory or
off 16-byte alignment. The host reports it — the trap's message, and whatever
location the module lets it recover — and goes back to where the player launched
the cart. **The frame the trap interrupted is never presented**: the player sees
the last whole frame, then the report. A trapped instance is never called again,
and a host keeps a trap from passing silently exactly as §4.3 requires of a Lua
error.

`quit()` unwinds the same way and is not a trap (§16.4).

### 16.9 Sample audio — `snd`

§8 is a tracker-shaped data model, which is right for authored carts and useless
for an emulated sound chip or a ported engine's mixer: those produce a sample
stream. So this binding's own audio surface is **samples, not the §8 data model**.
The §8 verbs stay in the table, and a cart may use both.

```c
i32 snd(i32 pcm, i32 nframes);   /* pcm: nframes of signed 16-bit mono,
                                    LITTLE-ENDIAN, at 22,050 Hz. Queues what
                                    the host has room for and returns how
                                    many; with nframes 0 it reads nothing and
                                    returns the room */
```

**22,050 Hz, mono, 16-bit** — the rate §8.3's synthesis is defined at. A browser or
desktop resamples to its device, which is `blit565`'s position again: the format
is fixed here and the host converts, never the cart tracking the device.

**The host holds 2,048 frames**, about 93 ms: that many frames the cart handed over
and the output has not yet taken. The cart refills the queue once per frame, so it
has to outlast the gap between two frames with room for a slow one. The depth is
also the most latency the queue adds; what an output does after it takes frames —
a DMA ring, a browser's audio thread — is its own latency, like a panel's, and does
not count against the 2,048.

**The return value is the clock.** The output drains the queue at its rate and the
cart fills it at its own pace, and neither may assume the other's: a cart that
makes a fixed count per tick drifts against the output, because two clocks never
agree, and starves it or overflows it. A cart that asks for the room (`snd(0, 0)`)
and fills it — or offers what it has and keeps what was not taken — tracks the
output exactly, whatever its frame rate. 0 means the queue is full for now;
nothing blocks (§16.4).

**Silence drains at the rate.** §8.3 already makes silence a valid rendering, so a
host without audio accepts and drops — and its queue still drains by the console's
clock, 22,050 frames a second, so the cart meets the backpressure it would meet
where the frames are played. A cart that paces itself on the stream, an emulator
syncing to its sound chip, runs at speed on a silent host. The cart cannot tell,
exactly as with `sfx`.

How the stream meets the console's own sound is the host's. libmoy's `moy_stream`
(`moy_audio.h`) is a queue mixed into the §8 synth's output after its channels and
under its master level. A `pcm` range outside linear memory is a trap, and a
negative `nframes` is such a range. Audio has no goldens (§8.3); what conformance
holds is the counts, which a stopped clock makes exact.

### 16.10 The cart's own work across the cores — `par`

```c
void par(i32 n, i32 arg, i32 stacks, i32 size);
    /* _par(i, arg) for every i in [0, n), across the host's cores; returns
       when every item has. Item i's C stack is the `size` bytes below
       stacks + (i + 1) * size */
```

A compiled cart's cost is its own loops, and the consoles that run it have more
than one core. `par` hands the host `n` items of that work — a band of a frame's
rows, a range of vertices — and returns when all are done. The host runs them on
the cores it gives the cart, the calling one included, at once and in any order. A
host with one core, or one that gives the cart only the calling core (a browser
page without cross-origin isolation), runs them there one after another, in order.
The cart cannot tell which, and its frame is the same either way.

**What the cart provides.** The export `_par(i32 i, i32 arg)` runs item `i`; `arg`
is `par`'s own, passed through, typically a pointer to the job. The cart also
exports its stack pointer as `__stack_pointer`, the mutable `i32` global that C,
C++, Rust and Zig all move their stack with (`-Wl,--export=__stack_pointer` with
clang). The host sets it to `stacks + (i + 1) × size` for item `i`, so every item
has a stack of its own whichever core runs it, and puts it back when the item
returns. `stacks` and `size` are multiples of 16 and the `n × size` bytes from
`stacks` lie in linear memory; otherwise `par` traps. A module that imports `par`
without both exports is refused before it runs.

**What an item may do** is compute over the cart's memory. It calls no import: one
that does traps, `par` included, so items do not nest. It writes no memory another
item reads or writes, and it uses no mutable global but its stack pointer: an item
on another core runs in an instance of its own, whose globals are as the module
declares them, so what the cart has to hand an item it hands over in memory.
Within those rules the result depends neither on the order nor on how many cores
ran it, which keeps a compiled cart's frames identical on every host (§16.11); an
item that breaks them makes the result host-dependent, as a NaN payload is.
Everything the cart wrote before calling `par` is visible to every item, and
everything the items wrote is visible when `par` returns: the host's join is the
only synchronisation a cart needs, so the profile stays without threads or
atomics.

**A trap** in any item traps the call to `par` with the message of the
lowest-numbered item that trapped, which is the one a host running them in order
stops at. A host lets every item it started finish first; items above the lowest
trap may or may not have run.

How many cores a host gives a cart, and how it shares the items among them, is
host policy. Why fork-join rather than threads is RATIONALE.md's.

### 16.11 Determinism

WebAssembly is deterministic except NaN bit patterns. The binding pins it with one
rule: **a conforming host may canonicalize NaNs; a conforming cart must not depend
on NaN payloads.** Everything else — integer arithmetic, `f32` rounding, linear
memory — is bit-identical across engines by the WebAssembly specification itself,
which makes this binding *easier* to hold to golden frames than Lua was: the frame
a cart blits is the frame the suite diffs, on every host. `par` keeps that: items
that follow its rules leave the same memory whatever their order and however many
cores ran them.

**This binding's goldens are RGB565 frames.** The palette-index goldens of §11
cannot represent a palette blit's 256 colours, so a compiled cart's scene is judged
on the frame as shown, reduced to RGB565 — each channel's high bits, `r >> 3`,
`g >> 2`, `b >> 3`, row-major, little-endian. It is the finest form every host
reproduces exactly: a direct-colour host holds it and an RGB888 host reduces to
it. Verbs reduce through the cart's palette, a `blit` through the palette it was
handed, and a `blit565` frame is already in the golden's form.
`conformance/wasm_run.py` holds a host to these scenes and to the refusals.
