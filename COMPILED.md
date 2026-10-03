# Your first compiled cart

A compiled cart is a moy cart written in C or C++ instead of Lua and compiled to
WebAssembly (SPEC.md §16). It calls the same verbs and plays in the same players,
and it can do what a Lua cart cannot: its own work on every pixel, every frame.
Reach for it when a Lua cart is too slow for what you want to draw; for anything
else, Lua is simpler ([GUIDE.md](GUIDE.md)).

## What you need

`moy`, as for any cart (GUIDE.md, part 1). The first build downloads the C
compiler, wasi-sdk 24, once: about 115 MB, checked by sha256, kept in moy's data
folder. Nothing else.

## 1. Make one

```
moy new --wasm plasma
moy play plasma.moy
```

A window opens on a moving plasma with a circle you steer with the arrows.
`moy play` built the cart first, and it keeps watching: save a file under
`src/` and it rebuilds and reloads. `moy web plasma.moy` is the same loop in the
browser player.

```
plasma.moy/
  manifest.json     "runtime": "wasm", and "memory": the cart's memory in 64 KB pages
  config.json       values a player can edit
  src/main.c        the game
  src/runtime.c     the heap and the C library's edges; you should not need to edit it
  src/moy_cart.h    every verb, declared for C
  main.wasm         what `moy build` made from src/ -- the cart's program
```

## 2. The code

The console calls three hooks, the same three a Lua cart has. In C you mark them
with `MOY_EXPORT`:

```c
MOY_EXPORT("_init")   void init(void) { }
MOY_EXPORT("_update") void update(float dt) { }
MOY_EXPORT("_draw")   void draw(void) { moy_cls(1); }
```

Every verb is a function with a `moy_` prefix: `moy_rect(x, y, w, h, c)`,
`moy_btn(MOY_LEFT, 0)`, `moy_print(text, length, x, y, c)`. An argument Lua lets
you leave out is passed explicitly, and `moy_cart.h` says the default beside each
one.

The starter's `_draw` fills a whole frame of palette indices itself and hands it
to the console with `moy_blit`, then draws over it with ordinary verbs. That is
the pattern for anything per-pixel. `moy_blit565` takes a frame of RGB565 colours
instead; use it only when your pixels really are full colour (shaded 3D,
photographs), because on small boards it is slower.

`malloc`, `snprintf`, `sinf` and the rest of the C library work. What does not is
anything that needs an operating system: there is no clock but `moy_time()`, no
file but the cart's own through `moy_read()` and the ones it keeps (below), no
`printf` to a terminal. If you use one by accident, `moy build` stops and names
it.

The cart's memory is fixed by `"memory"` in `manifest.json` and never grows: the
stack first (64 KB; `moy build --stack` changes it), then your static data, then
the heap. If the build says the memory is too small, raise it.

### Keeping files

A compiled cart can save: settings, save slots, a high-score table. List the
paths it writes in `manifest.json`, a folder ending in `/`:

```json
"writable": ["saves/", "options.cfg"]
```

`moy_write(path, path_len, data, len)` replaces a file whole and answers 0, or
-1 for a path you did not declare, -2 when the console has no room (or the file
is over 1 MB), -3 when its storage failed. `moy_read` reads the written copy
first, so you can ship a default `options.cfg` that the player's first save
replaces; `moy_erase` removes the copy, and the default comes back.
`moy_list(prefix, prefix_len, index, name, name_len)` names the cart's files one
at a time, in order, for a menu of save slots. The starter keeps where the
circle is in `saves/circle.bin`: press B, quit, play again.

A save is kept when `moy_write` returns, all of it or none of it, and it stays
when the cart is updated; it goes when the cart is removed. Where it lives is
the console's: `moy play` keeps a cart's files in moy's data folder, under
`files/` and the cart's name. Handle -2: the console's storage is shared, and
a save that does not fit should say so and let the game go on (SPEC.md §16.12).

## 3. Check it and share it

```
moy build plasma.moy     # what play and web do for you
moy check plasma.moy     # what the strictest console would say
moy export plasma.moy    # a web page that plays it
moy pack plasma.moy      # the folder as one file
```

Only `main.wasm` and the cart's data travel; `src/` is yours to share or not.

A compiled cart has no sprite sheet for an icon to point into, so give it a
cover: press **F7** while `moy play` runs it, and the frame on screen becomes
`cover.png`, its centre square at 128 × 128 (SPEC.md §3.6). A cover painted
elsewhere works too; `moy build` brings it into that shape.

## 4. On a board

A console runs a compiled cart only if it implements SPEC.md §16; one that does
not refuses it by name. On a Moybyte console, a board runs a compiled cart from a
module compiled for its chip, which Moybyte's `tools/push_cart.py` makes and
copies over:

```
python3 tools/push_cart.py plasma.moy --board tdeck
```

Your module is not signed by Moybyte, so turn on **Settings → Unknown sources**
on the console first; the push tells you when it is off. `moy push plasma.moy`
also reaches a console that answers it (proposals/sideload.md), and says so when
the console needs something only its own tools can build.

## 5. In 3D

```
moy new --jet cube
moy play cube.moy
```

is the same loop with a C++ starter: a cube drawn by Jet, CubeCoders' software
3D rasteriser (MIT), which `moy new --jet` fetches into `src/jet/`. Jet renders
straight into the frame the cart hands to `moy_blit565`.

## Where to look next

- SPEC.md §16 — the whole contract: every import, how a Lua verb becomes a C
  function, memory, traps, sound (`moy_snd`), more than one core (`moy_par`)
  and files (`moy_write`).
- `libmoy/include/moy_cart.h` — every verb, with its rules in one line each.
- RATIONALE.md, "The WebAssembly binding" — why it is built this way.
