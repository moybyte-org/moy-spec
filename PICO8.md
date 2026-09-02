# Importing a PICO-8 cart

You have a `.p8` or a BBS `.p8.png` and you want it to run as a moy cart. This
is the third door: [GUIDE.md](GUIDE.md) is for writing carts, [PORTING.md](PORTING.md)
for running them on your own hardware, and this one for bringing an existing
PICO-8 cart across.

**Read the licensing section before you publish anything you convert.**

## Converting one

The [rolling release](https://github.com/moybyte-org/moy-spec/releases/tag/player-latest)
is a single executable and needs no Python:

```
moy port cart.p8                       # -> cart.moy, beside it
moy port https://www.lexaloffle.com/bbs/cposts/1/15133.p8.png
moy port cart.p8 out.moy --title "Name"
moy play cart.moy                      # and there it is
```

It takes a BBS URL directly, so converting somebody's cart is one line with
nothing checked out. `moy demo` does the whole thing end to end — fetches
Celeste Classic, ports it, plays it — if you would rather see it than read
about it.

`--zoom` adds the `view(128,120)` hint, which crops 8 PICO-8 rows so a 4:3
handheld fills its height instead of letterboxing. It does not change a desktop
window.

From a checkout, the same conversion is `python3 moy.py port …`, and the porter
runs standalone as `python3 p8_lua_port.py cart.p8 out_dir [--title "Name"]`.

A host built on this may offer its own import — Moybyte's browser console takes
a dropped `.p8` and converts it in the page, with no install and no cable — but
`moy port` is what this repository ships.

## What does the work

Two scripts, both in this repository:

| | |
|---|---|
| `p8_import.py` | reads the cart. Parses `.p8` text and unpacks a `.p8.png` ROM (including the `pxa` and the older `:c:` code compression), and converts the sprite sheet, map, flags, sfx and music. |
| `p8_lua_port.py` | writes the cart. Emits `main.lua` — a PICO-8 compatibility shim, the cart's own code mechanically converted to Lua 5.4, and the data tables — plus the assets and a manifest. |

The output is an ordinary `"runtime": "lua"` cart declaring a `128x128` canvas,
so it draws real PICO-8 pixels 1:1 and the host does all scaling.

## What the importer decides before it writes

Every conversion starts with a **verdict**, read off the cart's own code
before a byte lands on disk:

| verdict | what a host does |
|---|---|
| **runs** | nothing the importer knows about is in the way |
| **runs with gaps** | imports; the reasons are listed beside the cart, so a flat pause menu or a zero on a debug HUD is not a mystery |
| **will not run** | refused, with the reasons — a cart that loads other carts, unpacks its data with 16.16 fixed-point shifts, or switches to a screen mode this console has no screen for. `--force` ports it anyway |

`moy port` prints it, `p8_lua_port.classify(sections)` returns it, and
`port_sections` hands it back beside the file list so a browser importer can
badge the card. It is a **static** reading — patterns over the converted code,
each one put there by a corpus cart that hit it — so it cannot see a cart that
errors on its first frame or generates a world for a minute; that is a dry
run's job, and the corpus table below records where the two disagree.

## How faithful is it, really

Faithful enough that most carts boot and play, and **not** an emulator. PICO-8
is a machine with a memory map; moy is a verb table with, since 2026-09, a
PICO-8 machine behind it for ported carts. Where a cart uses the API,
conversion is close to exact. Where it uses the *machine*, the machine is now
there: 64 KB of memory with the sheet, the map, the flags, both palettes,
camera, clip and the screen at their PICO-8 addresses, kept in step with the
console both ways (`libmoy/src/moy_p8.c`, measured in
[`proposals/p8-memory-map.md`](proposals/p8-memory-map.md)).

One number still matters up front: PICO-8 uses 16.16 fixed point, and this
runs on a Lua whose numbers are floats (`LUA_32BITS` — single precision — on
the C tier). Arithmetic differs in the last bits. Fine for nearly everything;
fatal for a cart that unpacks its data with fixed-point shifts or depends on a
fractional bitmask, and that is the one class the verdict refuses outright.

## What comes across cleanly

**The data.** Sprite sheet, the full 128×64 map (including the rows PICO-8
hides in the bottom half of `__gfx__`), sprite flags as `flags.moyflags`, all
64 sfx with their per-sfx filters and custom instruments, and the music
patterns. The manifest ships PICO-8's palette with its sixteen secret colours
at 16–31, so `pal(c, 128 + i)` lands on the real colour.

**The dialect.** The cart's Lua is converted token by token, not by regex:

| PICO-8 writes | becomes |
|---|---|
| `!=` | `~=` |
| `x += e`, and every other `op=` | `x = x + (e)` |
| `^^`, `>>>`, `\` (integer divide) | `~`, `>>`, `//` |
| `if (c) stmt` / `while (c) stmt` | `if c then stmt end` / `while c do stmt end` |
| `if c do ... end` | `if c then ... end` |
| `?"text"` | `print("text")` |
| `a \\ b` | `flr(a / b)` — an integer, so `x \\ 8 .. ","` prints `3,` and not `3.0,` |
| `0xffff`, `0x0.0001`, `0xA5A5.8` | the 16.16 bit pattern PICO-8 reads: `(-1)`, `(1/65536)`, `(-1515880448/65536)` |
| `@addr`, `%addr`, `$addr` | `peek(addr)`, `peek2(addr)`, `peek4(addr)` |
| `0b1010`, `0x1f`, `.5`, `0or` | Lua-legal numbers (PICO-8 has no exponent form, so `0or1` lexes as `0 or 1`) |
| `[[ long strings ]]` | quoted strings |
| P8SCII glyph bytes (`\x80`+) | named constants — the six button glyphs keep their identity, so `btn(➡️)` and `btn(⬆️)` stay distinct |
| `_init` / `_update` / `_update60` / `_draw` | `p8_*`, paced by the shim |

A cart defining `_update60` is declared as a 60 fps cart in its manifest, so
the host drives it at the rate it was written for.

**The API.** The shim implements PICO-8's verbs over the moy cart API —
`sin`/`cos` with their turn-and-flip semantics, the table verbs
(`add`/`del`/`foreach`/`all`/`count`), `btn`/`btnp` with PICO-8's auto-repeat,
`pal()` in every form including the table form and the **screen palette**
(`pal(c, d, 1)`, kept across frames as PICO-8 keeps it), `palt()` as real
transparency state (so `palt(0, false)` draws black), `fillp()` with its
two-nibble colours and its transparency bit, `oval`/`ovalfill`, `rnd()`
including the table form, string indexing, coroutines (`cocreate`, `coresume`,
`costatus`, `yield`), and the PICO-8 system font at its true 3×5, drawn by the
console in C where the machine is open.

**The machine.** `peek`/`poke`/`peek2`/`poke2`/`peek4`/`poke4`/`memcpy`/`memset`
address the real memory map; `sget`/`sset` and `mget`/`mset` read and write it;
`fget`/`fset` are the console's own flags; `reload`/`cstore` copy from and to a
ROM snapshot of the seeded image. A cart that bakes a texture by copying the
screen into the sheet, fades by `memcpy` into the palette, or draws a shadow by
`peek`/`poke` over `0x6000` does exactly that here.

## What is approximated

These convert, run, and do *something* — but not the thing PICO-8 did. The
verdict names them per cart.

| verb | what happens instead |
|---|---|
| `menuitem` | the pause menu is the console's; entries are not shown |
| `stat` | clock, CPU and audio counters read 0; the mouse reads nothing |
| `flip` | does nothing; the console calls `_draw()` for you. A cart whose whole loop is `flip()` with no `_update`/`_draw` is refused |
| sfx/music memory (`0x3100`–`0x42ff`) | remembered, not played; the imported sounds play |
| `sfx(n, ch, offset, len)` | the whole sound plays |
| `cstore` | writes the ROM snapshot in memory; nothing reaches the cart file |
| `0x5f2c` screen modes | the 64×64 and rotated modes are refused; the normal mode is a no-op |
| custom fonts (`0x5600`), bitplane masks (`0x5f5e`), sheet/screen remaps (`0x5f54`/`0x5f55`) | remembered, not applied |
| 16.16 arithmetic | the bit verbs (`band`, `shr`, `rotl`, …) work on the 32-bit fixed image, and a hex literal spells PICO-8's bit pattern (`0xffff` is −1, `0x0.0001` is 1/65536) — exact whenever the pattern fits float32's 24 bits, which fraction-packed flags and masks do. A data decoder built from shifts by 16 over full 32-bit words does not run |
| `cartdata` `dget` `dset` | **real** — they persist through the console's own save memory |
| `printh` `extcmd` `holdframe` | dropped |

## What cannot come across

| verb | why |
|---|---|
| `load` | the launcher swaps carts here; a multi-cart game is refused |
| `reboot` `stop` | there is no command line to drop to |
| `trace` `info` `serial` | no traceback to fetch, no console to print to, nothing on the other end of the port |
| `#include` | the included file does not travel with the cart |

## The test corpus

Twelve carts, chosen to stress *different* things rather than to be a top
twelve: a raycaster, a world-gen sim, a minified bytecode VM, carts whose
graphics live in packed strings. They are not in this repository — see
[`conformance/p8_corpus.json`](conformance/p8_corpus.json) for the links and
`conformance/fetch_p8_corpus.py` to cache them. `make -C libmoy p8-carts` runs
the gate.

**The gate is weak on purpose and you should not read it as "plays".** It
measures three things by comparing rendered frames: `runs` (no error), `animates`
(the frame changed between two run lengths) and `responds` (the frame differs
when a direction is held) — and beside them it records the importer's
**verdict**, pinned in `p8_carts_expected.json` like a golden, so the table
shows where the static call and the run disagree.

Every row below marked *played* was driven by a person, not inferred from the
gate.

| cart | verdict | runs | animates | responds | played |
|---|---|---|---|---|---|
| bunnysurvivor | runs | yes | yes | yes | **plays** — through, menus and all |
| crimson_night | runs | yes | yes | no | **plays** — its audio drove the sfx-filter work |
| picooffroad | runs | yes | yes | yes | **plays** — races, with its shadow and its fades, on the reference boards (2026-09) |
| petal_quest | runs | yes | yes | yes | **plays** from the title into its coroutine cutscenes, with its map (2026-09-02: coroutines, a `btnp` edge visible in `_draw`, `map()`'s whole-map default) |
| dungeons_and_diagrams | gaps | yes | yes | yes | **plays**; its packed-flag bit trick reads right now (16.16 bit verbs) |
| mossmoss | gaps | yes | yes | yes | starts; moss placement keys its walls by `x..","..y`, which needed integral floats to print as integers — to be re-played |
| lowmemsky | gaps | yes | yes | no | runs; no input — which is the cart, it makes no `btn` calls |
| dank_tomb | gaps | yes | yes | yes | boots to its title and takes input (2026-09-02: 16.16 bit verbs on its data parser, integer printing, the raw map bytes); to be played |
| terra_1cart | gaps | no | no | no | *(not played — generates its world past the harness's 45 s)* |
| celeste_classic_2 | refused | yes | yes | yes | starts; nothing moves, only the clouds draw — its levels are px9-packed 16.16 |
| nimudazus | refused | no | no | no | *(not played — errors decoding its bytecode)* |
| poom | refused | yes | yes | no | multi-cart; the loading screen draws through the memory map and stops there |

Eleven of twelve boot, three are refused up front and two of those would have
sat on a shelf looking broken. Of the nine that import, one the verdict calls
"gaps" still fails — on time, not on a verb — which is the honest edge of a
static reading. If you convert a cart and play it, the useful contribution is
a line in this table.

## Licensing

**PICO-8 BBS carts default to CC BY-NC-SA 4.0.** A converted cart is dev and
test material unless its own licence says otherwise: keep it out of anything you
ship, and put an attribution note beside it. The emitted manifest sets
`safe_to_share: false` so a host never has to infer that.

## A note for whoever maintains this

The converter runs on **two** Python-ish tiers: CPython on a desktop, and
MicroPython in a browser console, which is how a cart reaches a board that has
no cable. MicroPython decodes UTF-8 and only UTF-8 — it accepts a codec name,
ignores it, and raises on the first byte ≥ 0x80, and it ignores an `errors`
argument the same way. `.decode("latin-1")` is therefore correct on the desktop
and broken in the browser, which is exactly how every cart silently failed to
import there while the whole test suite passed. Decode bytes through
`_latin1()`, and when you add a check, run it on both tiers rather than
describing the rule in a comment.
