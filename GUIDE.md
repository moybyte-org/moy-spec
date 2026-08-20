# Writing games for moy

You have a cart to write. This is the door for you.

It is not the spec — SPEC.md is, and it settles every argument about what a
verb does. This is the part the spec deliberately leaves out: the order to do
things in, the tools around the folder, and the handful of things that will
surprise you once and then never again.

The other door is [PORTING.md](PORTING.md), for making a console that *runs*
carts rather than one that plays them.

**Part 1** builds a small game from nothing, one step at a time. **Part 2** is
the handbook — a section per topic, to come back to.

---

## Part 1 — Your first cart

We are writing Star Catcher: stars fall, you catch them, you miss three and it
is over. By the end it makes noise, keeps a high score across restarts, and is
tunable by someone who cannot read Lua.

### 0. What you need

`moy` from the [release download](https://github.com/moybyte-org/moy-spec/releases/tag/player-latest),
or a checkout of this repository and `python3 moy.py` in place of `moy`
everywhere below. Nothing else — no toolchain, no package manager, no
project file.

An editor with a Lua language server (VS Code's Lua extension, or anything
speaking LSP) is worth ten minutes of setup: the scaffold drops `moy-api.lua`
in your cart folder and that file is what turns every verb into autocomplete
and hover documentation.

### 1. Scaffold it

```
moy new star
moy run star.moy
```

Your browser opens on a moving circle. `moy run` is a local server plus the
web player; leave it running. Every time you save a file in the cart folder,
the game restarts — under a second, no rebuild, no refresh.

What `moy new` made:

```
star.moy/
  manifest.json     who this cart is and what it wants
  main.lua          the game
  config.json       values a player can edit; empty for now
  moy-api.lua       editor stubs, never executed, never shipped
```

That folder *is* the cart. Git tracks it, your editor opens it, `cp -r`
duplicates it. There is no build output and no packaging step you have to run
before it will play.

### 2. The loop

Delete the body of `main.lua` and start here:

```lua
function _init()   end       -- once, before the first frame
function _update(dt) end     -- once per tick; dt is seconds since the last one
function _draw()   end       -- once per frame
```

All three are optional and the console calls them in that order. The console
runs at 30 ticks a second unless the manifest asks for 60 (§5).

**Write motion as `speed * dt`, never as `speed`.** A host that falls behind
is allowed to skip draws while still updating at the full rate, and a host may
be running you at either tick rate. Multiplying by `dt` is what makes both of
those invisible in your game instead of a speed change.

### 3. Draw

Colours are palette indices, not RGB. `0` is black, `7` is white, `12` is
blue; the whole table is §2, and `palette.json` beside it is the same thing as
data.

```lua
local px, py

function _init()
  px, py = W // 2, H - 16
end

function _draw()
  cls(1)                          -- clear to dark blue
  circ(px, py, 7, 12)             -- you
  print("STAR CATCHER", 8, 8, 7)
end
```

`W` and `H` are the canvas size. **Read them; do not write 320 and 240.** The
day you try `"canvas": "128x128"` in the manifest, or copy code into a cart
that already declared one, every hard-coded 320 becomes a bug and every `W`
keeps working.

### 4. Read the buttons

```lua
function _update(dt)
  if btn("left")  then px = px - 140 * dt end
  if btn("right") then px = px + 140 * dt end
  if px < 8 then px = 8 elseif px > W - 8 then px = W - 8 end
end
```

`btn` is *held*. `btnp` is *pressed this frame* — one true per physical press,
and it does not autorepeat (§12.2 explains why, and what to write if you want
repeat). Use `btn` for movement, `btnp` for menus and firing.

Four directions plus `a` and `b` exist everywhere. `run` may not. Touch and
keyboard are enhancements you may add, but **the game has to be playable with
buttons alone** (§7.3) — that rule is what keeps one catalogue instead of one
per input device.

### 5. Things that fall

Lua tables are your only container, and they are 1-based.

```lua
local stars, spawn_in = {}, 0
local score, lives = 0, 3

function _update(dt)
  -- ... movement from step 4 ...

  spawn_in = spawn_in - dt
  if spawn_in <= 0 then
    spawn_in = 0.8
    stars[#stars + 1] = { x = 8 + rnd(W - 16), y = -4 }
  end

  for i = #stars, 1, -1 do            -- backwards: we remove as we go
    local s = stars[i]
    s.y = s.y + 70 * dt
    if s.y > py - 8 and math.abs(s.x - px) < 10 then
      table.remove(stars, i)
      score = score + 1
    elseif s.y > H then
      table.remove(stars, i)
      lives = lives - 1
    end
  end
end
```

`rnd(n)` gives a float in `[0, n)`; `flr` floors one to an integer. Draw with
`flr(s.x)` — the verbs take pixels, and a coordinate carrying a fraction is a
coordinate you cannot reason about.

`math`, `string` and `table` are all available. `io`, `os`, `require` and
friends are not, on any console, ever (§4.1). A cart is one script: there is no
importing a second file.

### 6. Make a noise

Sound lives in `sounds.json` beside `main.lua`. Write it by hand — it is small:

```json
{
  "sfx": [
    { "speed": 22, "steps": [[60, 0, 5], [67, 0, 4], [72, 0, 3]] },
    { "speed": 14, "steps": [[40, 3, 6], [28, 3, 4], [18, 3, 2]] }
  ],
  "music": []
}
```

A step is `[pitch, wave, volume]`. Pitch is a semitone index where 57 is
concert A; wave 0 is a square and wave 3 is noise; volume runs 0–7. `speed` is
steps per second. So effect 0 is a rising three-note blip and effect 1 is a
falling noise thud. `sfx(0)` on a catch, `sfx(1)` on a miss.

The full model — effects, looping, music rows, how channels are claimed — is
§8. Two honest warnings: there is **no authoring tool in this repository** for
sound (the known gap), and a console with no audio hardware plays your cart in
silence and still conforms, so nothing may depend on hearing it.

### 7. Remember the score

```lua
local best

function _init()
  best = pmem(0)                       -- 0 the first time, forever after not
end

-- when the run ends:
if score > best then
  best = score
  pmem(0, score)
end
```

256 slots, one signed 32-bit integer each, kept per cart (§9). That is the
whole persistence model. A slot you have never written reads 0, and a slot
index outside 0–255 reads 0 and silently discards writes — so keep a comment
naming what each slot holds; it is the only schema you get.

### 8. Tune it without touching code

`config.json` is a flat map of values, and `cfg(key, default)` reads it:

```json
{ "fall_speed": 70, "spawn_seconds": 0.8 }
```

```lua
local fall, gap

function _init()
  fall = cfg("fall_speed", 70)
  gap  = cfg("spawn_seconds", 0.8)
end
```

Always pass the default. Somebody will delete the file, and a cart that
crashes because its difficulty knob went missing is a cart that cannot be
handed to anyone.

Read config in `_init`, not in `_update` — a lookup per frame buys nothing.

### 9. Check it, then ship it

```
moy check star.moy
```

runs every test that is decidable from the cart's own bytes and reports what
the *strictest* conforming console would say: a manifest it would refuse, a
reach past the sandbox, a verb that is not core, a map larger than the format
allows. It is the cheapest possible way to find out that your game will not
run on a handheld you do not own.

Then pick a shipping form:

```
moy export star.moy      # a folder of static files that boots into the game
moy pack star.moy        # the folder as one file you can attach or link
moy push star.moy        # onto a connected console
```

`moy export` is the itch.io answer — zip the output folder, upload it as an
HTML5 game, done. `moy play star.moy` runs the native desktop player if you
would rather not use a browser.

Here is the finished `main.lua`, the pieces above assembled:

```lua
-- Star Catcher -- catch the falling stars, miss three and it is over.

local BG, STAR, YOU, INK = 1, 10, 12, 7

local px, py, stars, score, best, lives, spawn_in, over
local fall, gap

local function reset()
  px, py = W // 2, H - 16
  stars, score, lives, spawn_in, over = {}, 0, 3, 0, false
end

function _init()
  fall = cfg("fall_speed", 70)
  gap = cfg("spawn_seconds", 0.8)
  best = pmem(0)                       -- slot 0: best score
  reset()
end

function _update(dt)
  if over then
    if btnp("a") then reset() end
    return
  end

  if btn("left") then px = px - 140 * dt end
  if btn("right") then px = px + 140 * dt end
  if px < 8 then px = 8 elseif px > W - 8 then px = W - 8 end

  spawn_in = spawn_in - dt
  if spawn_in <= 0 then
    spawn_in = gap
    stars[#stars + 1] = { x = 8 + rnd(W - 16), y = -4 }
  end

  for i = #stars, 1, -1 do
    local s = stars[i]
    s.y = s.y + fall * dt
    if s.y > py - 8 and math.abs(s.x - px) < 10 then
      table.remove(stars, i)
      score = score + 1
      sfx(0)
    elseif s.y > H then
      table.remove(stars, i)
      lives = lives - 1
      sfx(1)
      if lives <= 0 then
        over = true
        if score > best then
          best = score
          pmem(0, score)
        end
      end
    end
  end
end

function _draw()
  cls(BG)
  for i = 1, #stars do
    circ(flr(stars[i].x), flr(stars[i].y), 3, STAR)
  end
  circ(flr(px), py, 7, YOU)
  print("SCORE " .. score, 8, 8, INK)
  print("BEST " .. best, 8, 18, 6)
  print("LIVES " .. lives, W - 72, 8, INK)
  if over then
    print("GAME OVER - PRESS A", W // 2 - 76, H // 2, INK)
  end
end
```

Seventy lines, no art, no dependencies, and it runs on every conforming
console.

---

## Part 2 — The handbook

### The cart, file by file

| file | | |
|---|---|---|
| `manifest.json` | required | title, and what the cart needs from the host (§3.1) |
| `main.lua` | required | the game; `"main"` in the manifest renames it |
| `sprites.moygfx` | optional | the sprite sheet, as text (§3.2) |
| `map.moymap` | optional | the tilemap, as text (§3.3) |
| `sounds.json` | optional | effects and music (§8.1) |
| `config.json` | optional | your own tuning values, read by `cfg` |
| `moy-api.lua` | never shipped | editor stubs; `moy pack` drops it for you |

Everything is text, so every one of these diffs, merges and reviews like
source. That is the reason for the formats, not an accident of them.

The manifest fields worth knowing on day one: `title`, `fps` (30 or 60),
`canvas`, `input`, and `icon` — the last names tiles from your own sheet for a
launcher to draw the cart by (§3.4). A host ignores manifest keys it does not
know, so vendor tools can annotate your cart without breaking it anywhere else.

### The loop, and time

`_init` once, then `_update(dt)` and `_draw()` per tick, in that order.

`time()` gives milliseconds since the cart started, which is what you want for
animation phase and cooldowns that must not drift. `dt` is what you want for
movement. Mixing them up produces a game that is subtly wrong at one of the two
tick rates.

Declaring `"fps": 60` is a request, not a guarantee — a host that cannot hold
60 for your cart runs it at 30 rather than somewhere unstable in between (§5).
Anything that only feels right at 60 will feel wrong somewhere.

A Lua error ends the cart and the host reports it with your line number (§4.3).
There is no `pcall`-and-limp-on culture here; the console would rather stop.

### The canvas, and the three sizes

320 × 240 by default. A manifest may declare `"160x120"` or `"128x128"` and the
whole console shrinks to it — verbs clip to it, `W`/`H` report it. The set is
closed at those three (§1), so a host can pick its scaler ahead of time.

`view(w, h)` is the runtime cousin: it declares that you only use a centred
region, which lets a console with a bigger screen blow that region up instead of
letterboxing it. `background(c)` declares a backdrop rather than clearing to one
every frame. Both always work everywhere; consoles differ only in how much they
make of them, which is §6's reason for keeping them core and ungarded.

Your cart never learns the physical resolution of the glass, and should never
try to.

### Colour

64 indices. 0–15 are the classic base 16 — a converted PICO-8 cart keeps its
colours byte for byte — and 16–63 extend them (§2).

- `pal(c0, c1)` remaps at *draw time*: pixels already on the canvas do not
  change. There is no display-time palette to flash the screen with (§12.1); to
  flash, draw differently for a few frames.
- `palt(c, on)` marks an index transparent for sprites.
- Both reset when called with no arguments — do that rather than tracking what
  you set, especially before drawing your HUD.
- A cart may replace the whole 64-entry table from its manifest (§2.2) if the
  default palette is wrong for your art.

**Sprites can only use indices 0–15** (§2.3); primitives and text can use all
64. If you want a sprite in a colour past 15, `pal` one of the low indices onto
it at draw time.

### Sprites

The sheet is 512 tiles of 8 × 8, sixteen to a row, and it is a text file of hex
nibbles. §3.2 has the arithmetic that turns a tile id into a position on it —
worth knowing if you generate art, and ignorable if you draw it.

Use your own art tool:

```
moy gfx star.moy                          # sheet -> star-sheet.png
moy gfx star.moy --import sheet.png       # PNG -> sheet
```

The PNG is indexed and 128 pixels wide. Aseprite, GIMP and Piskel all round-trip
it. Colours outside the cart's first 16 get snapped to the nearest index on
import and the tool tells you how many were.

```lua
spr(n, x, y, colorkey, scale, flip)
```

`colorkey` is the index to treat as transparent, `-1` (the default) for opaque.
`scale` is an integer. `flip` is 0/1/2/3 for none/horizontal/vertical/both. A
sprite bigger than one tile is drawn as adjacent `spr` calls — there is no
multi-tile sprite type, and a plain loop is the intended way to draw many
(§7.1).

`sspr` stretches an arbitrary pixel region to an arbitrary size, and is
**provisional** (§6.1): implemented everywhere here, but not core 0.2 yet. A
cart using it may not run on a console that shipped strictly to core, and
`moy check` warns you.

### The tilemap

One grid, up to 128 × 128 cells, one byte per cell. **Cells hold tile ids
0–254**, while `spr` reaches the full 0–511 (§3.3) — the low half of the sheet
is level geometry, the high half is where your animation frames live.

```
moy map star.moy --out level.csv          # map -> CSV
moy map star.moy --import level.csv       # CSV -> map
moy map star.moy --tiled                  # ... in Tiled's own CSV convention
```

Tiled edits the CSV directly. `--tiled` is not a conversion so much as the
absence of one: Tiled's export is already 1-based with 0 for empty, which is
exactly what a `.moymap` cell stores.

```lua
map(mx, my, w, h, sx, sy, colorkey, scale)   -- blit a region
mget(x, y)                                    -- read a cell; -1 if empty
mset(x, y, tile)                              -- write one; negative clears
```

Two things worth internalising. **Draw the level with one `map` call, not a
loop over cells** — a console is free to turn that into a single blit, and a
per-cell loop takes the opportunity away. And **the map is mutable state**: a
wall that crumbles is an `mset`, not a parallel array you have to keep in step.
`examples/brick_siege.moy` is built on both ideas and is worth reading.

### Input

Logical buttons, mapped by each host onto whatever hardware it has (§7.3):
`left` `right` `up` `down` `a` `b` always exist, `run` may not.

```lua
btn(name, player)     -- held
btnp(name, player)    -- pressed this frame, once per press
players()             -- how many controllers; always at least 1
```

Local multiplayer is core and needs no declaration: ask `players() >= 2` at
runtime and offer versus mode or don't. That is why a two-player cart is not
refused at load time by every single-controller console. Player 0 is always the
console's own controls, so single-player carts never pass the argument.

`touch()`, `key()`/`keyp()` and `textmode()` exist where the hardware does.
List what you read in the manifest's `"input"` so a host can draw soft controls
and warn a player up front — but it is never a requirement, and buttons alone
must be enough.

**The host owns exit.** Do not draw a QUIT button because you think the player
needs one; they can always leave. `quit()` is for ending your *own* cart — a
menu's exit row, a game-over screen — and it is mandatory only if you hold
`textmode(true)`, because then every key is text and the host's own gesture may
be unreachable (§9).

### Sound

Four channels. Music claims them from the top and effects round-robin what is
left, so an effect never cuts your background loop (§8).

- An **SFX** is a list of `[pitch, wave, vol]` steps with a `speed` in steps per
  second, optionally looping from `loop_start`.
- A **music track** is a list of rows, each row one SFX id or up to four, one
  per channel, `-1` for silence. `speed` is rows per second.
- A fourth number on a step is a **per-note effect** — slide, vibrato, drop,
  fades, two arpeggios — numbered as PICO-8 numbers them, so a ported cart's
  effect column carries straight over (§8.1).

Write the JSON by hand or generate it from a script; there is no editor here
yet. Audio is deliberately outside pixel conformance (§8.3): two consoles will
not produce identical samples, and one with no audio hardware produces none.
Never gate progress on a sound being heard — that is not a hypothetical, and
[PURR OS](https://github.com/PastorCatto/PURR-OS-ESP32) is the example: it binds
every audio verb and plays nothing, because the board has no audio output wired
up yet. Your cart runs there. It just runs quietly.

### Saving, and the config file

`pmem` is 256 signed 32-bit integer slots, per cart. Writes may be deferred by
the host but must land before your cart exits (§9). Pack booleans into bits if
you need more than 256 facts; do not expect to store a string.

`config.json` + `cfg(key, default)` is the surface you expose to a person who
will never open `main.lua`. Difficulty, enemy counts, an attract mode. It is
your cart's tuning file, not a system feature, and nothing enforces its shape —
so always pass a default.

### Layers

```lua
local world = make_layer(640, 240)
if world then
  -- a full drawing API, with its own camera, clip, pal and palt
  draw_layer(world, camx, 0)
end
```

One full-screen layer is guaranteed by the memory floor (§1.1), so the first
`make_layer` succeeds everywhere. A second may return nil, and that is an
ordinary allocation failure to test for — not a missing verb to guard against.
Draw a wide level once, window-copy it per frame.

A layer carries its own draw state, so whatever you point its camera at, the
screen's stays where you left it.

### Staying inside the console

The host reserves a fixed budget and your cart lives inside it (§1.1). The
parts that matter to you:

- **The heap is the shared resource.** Everything Lua allocates comes out of one
  pool. A deliberately heavy cart — hundreds of actors with closures, per-frame
  string garbage, a full-screen layer, a full-size map — was measured well
  inside it, so this is generous rather than tight. You have to work at
  overrunning it, but a per-frame `..` in a loop over every entity is how you
  would start.
- **Numbers are 32-bit** (§4.2). Integers wrap around two billion; floats carry
  about seven significant digits. Accumulating a position by adding a small
  float every frame for ten minutes will visibly quantise. Where it matters,
  keep the integer part separate.
- **`print` costs the same as anything else**, but text is always 8 pixels and
  there is no scale parameter. Big text is sprites.
- **You cannot read the framebuffer back** (§12.6). No `pget`, no blur-by-
  reading-the-screen. Keep the state you need in Lua, or draw into a layer you
  own.
- **Prefer one `map` call and plain `spr` loops** to anything clever. The
  batch-drawing verbs that used to be proposed were deleted because measurement
  said the loop was already cheap enough (§6.1).

### What `moy check` tells you

Three levels, and the distinction is the useful part:

- **error** — a strict console may refuse this cart. A manifest field that is
  wrong, a reach past the §4.1 sandbox, an undeclared extension, a map bigger
  than the format allows, a cart that cannot be played with buttons alone, a
  `textmode` cart with no `quit()`.
- **warn** — it will run, but not everywhere or not as you meant. A provisional
  §6.1 verb, an input kind you read but did not declare, an icon pointing past
  your sheet, a tile id the map cannot hold.
- **info** — sizes and fixed allocations, for orientation.

Anything it cannot decide from your bytes — whether the heap fits at level 7,
whether the game is any *good* with only buttons — it reports as a signal and
says so. Run it before every release; it is instant.

### Coming from PICO-8

```
moy demo                    # fetch Celeste Classic, port it, play it
moy port cart.p8            # port a cart of your own -> cart.moy
moy port cart.p8 --zoom     # ... and add the view() hint below
moy demo --zoom             # the demo takes it too
```

Assets come over nearly verbatim, because the sheet format *is* PICO-8's and
the first sixteen palette entries are PICO-8's. Code is mechanically translated
to Lua 5.4 and runs under a compatibility shim.

A port declares `"canvas": "128x128"` and draws native PICO-8 pixels; the host
scales. `--zoom` adds a `view(128, 120)` hint so a 4:3 console fills its height
at 2×, trading away eight centred rows top and bottom on hosts that honour it.

Things that will not carry over unchanged: anything reaching for `peek`/`poke`
or the PICO-8 memory map, `pget`, and code depending on 60 Hz. And note the
licensing — BBS carts are personal/dev material and their default licence is
CC BY-NC-SA.

### Gotchas

The short list of things that catch everyone exactly once.

1. **`btnp` does not autorepeat.** Menus that scroll on a held direction need
   your own timer (§12.2).
2. **Sprites are limited to indices 0–15**, everything else gets all 64. A
   sprite that must be colour 40 is a `pal` at draw time.
3. **Map cells stop at tile 254; `spr` goes to 511.** Art above 254 cannot be
   placed on a level (§3.3).
4. **`print` walks bytes, not characters.** ASCII 0x20–0x7F only; a two-byte
   UTF-8 character occupies two blank cells. Non-ASCII text is art from your
   own sheet (§6).
5. **`W` and `H`, never 320 and 240.** The moment a cart declares a canvas, the
   constants are wrong and the reads still work.
6. **`camera` returns the previous offset**, so save-and-restore needs no
   variable of your own:

   ```lua
   local ox, oy = camera(x, y)
   -- draw in world space
   camera(ox, oy)
   ```
7. **`clip` is screen space and applies after `camera`.** Clipping in world
   coordinates is a bug that passes both features tested separately.
8. **Reset `pal` and `palt` before your HUD.** They are global draw state and
   they outlive the entity that set them.
9. **A pmem slot outside 0–255 reads 0 and swallows the write.** No error.
10. **Audio may be silence and still conform.** Never gate anything on hearing
    it (§8.2).
11. **Lua tables are 1-based**, and `#t` on a table with holes is not what you
    want. Remove backwards when iterating.
12. **There is no `require`.** One script. Long files are the idiom here; the
    examples in this repository are single files on purpose.

### Where to look next

- `examples/brick_siege.moy` — a complete game in core only, heavily commented,
  written to be read.
- `examples/verbs.moy` — one screen per verb group. `moy run examples/verbs.moy`
  is the fastest way to see what each verb actually draws.
- `moy-api.lua` — every verb with its signature, in your editor.
- **SPEC.md** — the exact answer to anything above. §6, §7 and §9 are the verb
  tables; §12 is where the surprising decisions are argued.
- **RATIONALE.md** — why each fixed number is that number.
