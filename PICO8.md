# Importing a PICO-8 cart

You have a `.p8` or a BBS `.p8.png` and you want it to run as a moy cart. This
is the third door: [GUIDE.md](GUIDE.md) is for writing carts, [PORTING.md](PORTING.md)
for running them on your own hardware, and this one for bringing an existing
PICO-8 cart across.

**Read the licensing section before you publish anything you convert.**

```
python3 p8_lua_port.py cart.p8 out_dir [--title "Name"]
```

Two scripts do the work, both in this repository:

| | |
|---|---|
| `p8_import.py` | reads the cart. Parses `.p8` text and unpacks a `.p8.png` ROM (including the `pxa` and the older `:c:` code compression), and converts the sprite sheet, map, flags, sfx and music. |
| `p8_lua_port.py` | writes the cart. Emits `main.lua` — a PICO-8 compatibility shim, the cart's own code mechanically converted to Lua 5.4, and the data tables — plus the assets and a manifest. |

The output is an ordinary `"runtime": "lua"` cart declaring a `128x128` canvas,
so it draws real PICO-8 pixels 1:1 and the host does all scaling.

## How faithful is it, really

Faithful enough that most carts boot and play, and **not** an emulator. PICO-8
is a machine with a memory map; moy is a verb table. Where a cart uses the API,
conversion is close to exact. Where it uses the *machine* — poking video memory,
reading sheet pixels back, counting CPU — there is nothing underneath to be
faithful to, and those carts break in ways no amount of shim work fixes.

One number matters up front: PICO-8 uses 16.16 fixed point, and this runs on a
Lua whose numbers are floats (`LUA_32BITS` — single precision — on the C tier).
Arithmetic differs in the last bits. Fine for nearly everything; fatal for a
cart that depends on exact fixed-point overflow or on a fractional bitmask.

## What comes across cleanly

**The data.** Sprite sheet, the full 128×64 map (including the rows PICO-8
hides in the bottom half of `__gfx__`), sprite flags, all 64 sfx with their
per-sfx filters and custom instruments, and the music patterns.

**The dialect.** The cart's Lua is converted token by token, not by regex:

| PICO-8 writes | becomes |
|---|---|
| `!=` | `~=` |
| `x += e`, and every other `op=` | `x = x + (e)` |
| `^^`, `>>>`, `\` (integer divide) | `~`, `>>`, `//` |
| `if (c) stmt` / `while (c) stmt` | `if c then stmt end` / `while c do stmt end` |
| `if c do ... end` | `if c then ... end` |
| `?"text"` | `print("text")` |
| `@addr`, `%addr`, `$addr` | `peek(addr)`, `peek2(addr)`, `peek4(addr)` |
| `0b1010`, `0x1f`, `.5`, `0or` | Lua-legal numbers (PICO-8 has no exponent form, so `0or1` lexes as `0 or 1`) |
| `[[ long strings ]]` | quoted strings |
| P8SCII glyph bytes (`\x80`+) | named constants — the six button glyphs keep their identity, so `btn(➡️)` and `btn(⬆️)` stay distinct |
| `_init` / `_update` / `_update60` / `_draw` | `p8_*`, paced by the shim |

A cart defining `_update60` is declared as a 60 fps cart in its manifest, so
the host drives it at the rate it was written for.

**The API.** The shim implements PICO-8's verbs over the moy cart API —
`sin`/`cos` with their turn-and-flip semantics, the table verbs
(`add`/`del`/`foreach`/`all`/`count`), flag-masked `map()`, `btn`/`btnp` with
PICO-8's auto-repeat, `pal()` including the table form, `rnd()` including the
table form, string indexing, and the PICO-8 system font at its true 3×5.

## What is approximated

These convert, run, and do *something* — but not the thing PICO-8 did. The
importer reports them per cart, so you see the list for the cart in front of you.

| verb | what happens instead |
|---|---|
| `peek` `poke` `peek2/4` `poke2/4` `memcpy` `memset` | read and write 64K of **scratch** memory. A cart keeping its own bookkeeping there works; one poking a hardware register or blitting to the screen changes nothing. |
| `sget` | reads back 0 — the sheet is a *file* here, not memory. Collision or effects driven off sheet pixels will be wrong. |
| `sset` | dropped; `spr()` keeps drawing the art as imported. |
| `fillp` | the pattern is remembered but fills are solid, so dithered gradients come out flat. |
| `fset` | dropped — flags are baked in read-only, though `fget` works. |
| `flip` | does nothing; the console calls `_draw()` for you. **A cart that loops on `flip()` still needs that loop moved into `_update()`.** |
| `stat` | machine counters read 0 and the mouse reads nothing, so a debug HUD shows zeroes. |
| `cartdata` `dget` `dset` | **real** — they persist through the console's own save memory. |
| `reload` `cstore` | nothing to re-read; the sheet and map are files. |
| `printh` `extcmd` `holdframe` | dropped. |

## What cannot come across

| verb | why |
|---|---|
| `cocreate` `coresume` `costatus` `yield` | the console's Lua does not open the coroutine library. Rewrite that part as a state machine driven from `_update()`. |
| `reboot` `load` | the launcher swaps carts here; reset your own state instead. |
| `stop` | there is no command line to drop to. |
| `trace` | no traceback to fetch; the cart error screen shows the line. |
| `info` `serial` | no console to print to, nothing on the other end of the port. |

Beyond the verb list, three shapes of cart do not survive:

- **Carts that render by poking video memory.** The screen is not addressable.
- **Carts whose world is bigger than the 128×64 map**, built by streaming rows
  through memory the importer has no equivalent for.
- **Carts driven by coroutines**, which is usually a scene or cutscene system.

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
when a direction is held). A cart can pass all three and still be unplayable —
two below do.

| cart | runs | animates | responds | actually |
|---|---|---|---|---|
| bunnysurvivor | yes | yes | yes | **plays** — played through, menus and all |
| crimson_night | yes | yes | no | **plays** — played through; its audio drove the sfx-filter work |
| dungeons_and_diagrams | yes | yes | yes | passes the gate; nobody has sat down with it |
| mossmoss | yes | yes | yes | starts, but you cannot leave the first room |
| celeste_classic_2 | yes | yes | yes | starts, but nothing moves and only the clouds draw |
| lowmemsky | yes | yes | no | procedural, takes no input by design |
| poom | yes | yes | no | Doom demake — renders by poking screen memory |
| petal_quest | yes | no | no | coroutine-driven scenes; borderline past its title |
| picooffroad | yes | no | no | runs, frame never changes |
| dank_tomb | no | no | no | `_init` errors — reads level data as raw memory |
| nimudazus | no | no | no | Tempest 2000, minified into a bytecode VM |
| terra_1cart | no | no | no | hangs — world taller than the 128×64 map |

So: **9 of 12 boot, 7 of 12 animate, and 2 are confirmed played by a human.**
Everything else in the "actually" column above is either a known break or an
absence of evidence — including one cart that passes all three signals and
which nobody has played.

That gap is the honest summary of this document. Booting is cheap, playing is
not, and only a person with the cart in front of them can tell you which one you
have. If you convert a cart and play it, the useful contribution is a line in
this table.

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
