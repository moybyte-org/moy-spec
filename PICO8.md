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
moy port 15133.p8.png                  # a BBS cart you downloaded
moy port cart.p8 out.moy --title "Name"
moy play cart.moy                      # and there it is
```

It takes a file, never a URL: moy downloads nothing from the BBS, whose
[terms of use](https://www.lexaloffle.com/info.php?page=tos) ask for a person
in a browser, not a script. Download the cart from its BBS page, then port it.
`moy demo` does the rest end to end for Celeste Classic — it says where to
download the cart, then ports it and plays it — if you would rather see it
than read about it.

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
| `p8_import.py` | reads the cart. Parses `.p8` text and unpacks a `.p8.png` ROM (including the `pxa` and the older `:c:` code compression) and its label, and converts the sprite sheet, map, flags, sfx, music and label. |
| `p8_lua_port.py` | writes the cart. Emits `p8.lua`, the data tables and the PICO-8 compatibility shim; `main.lua`, the cart's own code mechanically converted to Lua 5.4; one more script per PICO-8 **tab** past the first — plus the assets and a manifest listing them all in `sources` (SPEC.md 4). |

The output is an ordinary `"runtime": "lua"` cart declaring a `128x128` canvas,
so it draws real PICO-8 pixels 1:1 and the host does all scaling. It also ships
its own 64-colour table (SPEC.md 2.2) — PICO-8's sixteen, the secret sixteen at
16–31, and the duplicates a `pal()` reaches — so a host that resolves indices
itself has to read `palette` from the manifest. The three loaders here do
(`moy_manifest_palette`); one that does not draws every converted cart in the
console's own colours, which looks like the cart's art is wrong rather than the
player.

**The generated half is its own file, because `main.lua` should be the cart.**
Line 1 of `main.lua` is the author's line 1, so a crash names a line they can
find and an editor opens a game instead of 1,300 lines of generated stdlib.
That cut cannot fall anywhere else: the shim captures the data tables as
upvalues when its chunk loads, so those travel with it, and `main.lua`'s
`local` aliases only reach code in their own chunk, so those travel with the
game.

### Tabs are files

PICO-8 keeps a cart's code in numbered **tabs**, separated in the file by a
line that reads `-->8`. That is where the author put the cart's structure —
*dungeons_and_diagrams* opens its four at `--menu`, `--tutorial`, `--board`,
`--puzzles list` — so each tab becomes a source of its own, in tab order, tab 0
being `main.lua`. A tab titled by its first comment line takes that name
(`board.lua`); anything else takes the number PICO-8 itself shows (`tab3.lua`).

It works because a PICO-8 cart's top-level names are **globals** by
construction — p8 Lua has no module scope to hide them in, and a tab writes
`board = {}` — so they cross a chunk boundary exactly as the shim's own globals
do. Where they would not, the tabs stay in one `main.lua` and the import report
says which of three it was: a top-level `local` in one tab that a later tab
reads (separate chunks would make it nil, silently, in code the author *did*
write), a top-level `goto` and its label in different tabs, or a long string
holding a line that reads `-->8` — PICO-8 splits for display and joins to run,
so a string may legally span a tab boundary there.

`#include` is a different thing and is refused — see *What cannot come across*
for why an included file cannot travel with a cart at all.

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
is a machine with a memory map; moy is a verb table with a PICO-8 machine
behind it for ported carts. Where a cart uses the API, conversion is close to
exact. Where it uses the *machine*, the machine is there: 64 KB of memory with
the sheet, the map, the flags, both palettes, the pen, the print cursor, the
fill pattern, camera, clip and the screen at their PICO-8 addresses, kept in
step with the console both ways (`libmoy/src/moy_p8.c`, measured in
[`proposals/p8-memory-map.md`](proposals/p8-memory-map.md)).

A Lua-to-C call floors at ~1.65 µs on the boards, which is where the shim's
cost went: every p8 draw and input verb is ONE crossing into the machine, which
resolves p8's defaults, floors, the draw palette, the fill pattern and the clip
from its own memory. `all`/`foreach`, the number verbs, the 16.16 bit verbs,
`peek`/`poke`, `mget`/`fget` and the native `|`/`&` operators are C for the same
reason, and the lookup-table span `poke(a, peek(lut | peek(a)))` over a range
folds into a single call. The shim keeps its Lua as the fallback for a host
without the machine, and `libmoy/test/p8lib.moy` holds both lanes to one
answer.

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

**The label, as the cover.** A PICO-8 label is 128 × 128, which is exactly a
cover's size (SPEC.md §3.6), so it becomes `cover.png` pixel for pixel: indexed,
its PLTE PICO-8's sixteen and then the secret sixteen — every colour a label can
hold — in the label's own numbering. A `.p8` carries it as `__label__`; a
`.p8.png` carries it as the picture itself, the 128 × 128 at (16, 24) of the
160 × 205 cartridge, inside a one-pixel near-black frame. The cartridge's
steganography owns each channel's two low bits, so a pixel is matched on the
high six, and a cart saved before PICO-8 changed its green (`#00E756`) gets the
nearest colour. `libmoy/test/p8_label_check.py` pins the region on a cartridge it
builds and on every real one to hand. A cart with no label, or an all-black
one, gets no cover, and the sheet's first non-blank tile stays its icon
(SPEC.md §3.4) either way.

**The dialect.** The cart's Lua is converted token by token, not by regex:

| PICO-8 writes | becomes |
|---|---|
| `!=` | `~=` |
| `x += e`, and every other `op=` | `x = x + (e)` |
| `^^`, `>>>`, `\` (integer divide) | `~`, `>>`, `//` |
| `if (c) stmt` / `while (c) stmt` | `if c then stmt end` / `while c do stmt end` |
| `if c do ... end` | `if c then ... end` |
| `?"text"` | `print("text")` |
| `a \\ b` | `flr(a / b)` — an integer, so `x \\ 8 .. ","` prints `3,` and not `3.0,`. It is a MULTIPLICATIVE operator, left-associative beside `*`, `/` and `%`, so `a*b\\c` is `(a*b)\\c` and `v\\26^i` is `v\\(26^i)` — `crimson_night` unpacks its high-score names with the second |
| `0xffff`, `0x0.0001`, `0xA5A5.8` | the 16.16 bit pattern PICO-8 reads: `(-1)`, `(1/65536)`, `(-1515880448/65536)` |
| `@addr`, `%addr`, `$addr` | `peek(addr)`, `peek2(addr)`, `peek4(addr)` |
| `0b1010`, `0x1f`, `.5`, `0or` | Lua-legal numbers (PICO-8 has no exponent form, so `0or1` lexes as `0 or 1`) |
| `[[ long strings ]]` | quoted strings |
| `// a comment` | `-- a comment`. p8 takes `//` as a line comment and has no `//` operator to confuse it with — integer divide there is `\`. Lua 5.4 has the operator and not the comment, so every one of these used to come out a DIVISION: `x=1 // why` became `x=flr(1/why)` |
| `\*`, `\#`, `\-`, `\|`, `\+`, `\^` in a string | the P8SCII control byte each stands for, spelled `\001`..`\006`. Lua knows none of these escapes — `"\^c1"` refuses to load — and escaping the BACKSLASH instead made the cart PRINT the command instead of obeying it, which is how `\^c` (clear the screen) and `\#` (solid background) came out as text in nine of the twenty-one corpus carts. Three digits always, because Lua reads up to three: `"\6"` followed by `1` is byte 61 |
| P8SCII glyph bytes (`\x80`+) | named constants — the six button glyphs keep their identity, so `btn(➡️)` and `btn(⬆️)` stay distinct |
| a glyph beside a name (`p1➡️`, `❎_down`) | ONE mangled name (`p1_p8g145`, `_p8g151_down`). p8's lexer reads a high byte as a letter, so a glyph touching an identifier is part of it; a glyph standing alone is still the value above |
| `_init` / `_update` / `_update60` / `_draw` | `p8_*`, paced by the shim |

A cart defining `_update60` is declared as a 60 fps cart in its manifest, so
the host drives it at the rate it was written for: one `_update` call from the
host is one PICO-8 tick, and the host's own scheduler places those ticks (§5).
The shim keeps `_draw` from running before the first tick, because PICO-8 never
draws before its first update and carts rely on it. A cart with no update
function draws every frame, as PICO-8's does.

One whole STATEMENT is rewritten rather than a token: `for a = i, j do
poke(a, peek(lut | peek(a))) end`, the lookup-table span a cart lights or
tints a run of screen memory with, becomes `__p8_lut_span(i, j, lut)` — one
call for 8,192 bytes instead of three to five per byte. The match is exact and nothing near it moves: the same
variable in all three places, no third `,step`, nothing else in the body, and
bounds and table that are names, numbers, fields, indexes or arithmetic and
never a call — because the fold evaluates them once where the loop evaluated
them every iteration. The porter's own `flr(…)` operand wrappers and redundant
parentheses are seen through. `__p8_lut_span` is the shim's, and its Lua body
IS that loop, so a host with no C behind the name runs exactly what it ran
before; `libmoy/src/moy_p8.c` answers false for anything but three plain
integers, which is when the loop takes over again.

**The operators.** PICO-8 has nine native bit operators (`| & ^^ ~ << >> >>>
<<> >><`); Lua 5.4 has six, refuses every one of them on a non-integral
number, and has no rotate at all. **They are the nine VERBS under another
spelling** — the manual's "operator versions are also available" — and the
porter emits ONE call each (`__p8_bor(a, b)`, `__p8_shl`, `__p8_rotl`) bound to
`band`, `shl`, `rotl`. One lane: `x >> 1` and `shr(x, 1)` cannot answer
differently, and a cart that takes `shr` for itself still gets p8's operator. A
call knows Lua's precedence, which is what a wrapper around each operand
cannot: `a + 1 & b` takes both sides of the `+`, `#t & 3` must not take `t`,
and `x &= y` must be rewritten at all.

An operand that is an integer already — a byte out of `peek`, a cell out of
`mget`, a one-argument `fget`, a literal, another such operator — keeps the
bare Lua instruction, but **only under `&`, `|` and `^^`**, which is what dank
tomb's `peek(...) & 0xf0` comes out as. Those three cannot move a bit across
the point or off the end of the image, so two integers meeting in one of them
answer the same in either arithmetic. The other six can, and no pair of
integers is enough for them: `3 >> 1` is 1.5, `~3` is −3.0000153, `1 << 15` is
−32768. The integer claim is a claim about the shim's own verbs, so a cart
that defines, declares, assigns or takes as a parameter a name like `peek`
turns the rule off for that name.

That reading is newer than the port (2026-09-10). Before it the operators were
a SECOND implementation — `flr()` on each operand and then Lua's own integer
operator — which floored away every fraction p8 carries, made `>>` logical
where p8's is arithmetic, and answered `shr(3, 1)` as 1 where the verb of the
same name said 1.5. Nothing caught it because the test pinned the two COPIES of
that reading to each other rather than to PICO-8. It is why celeste 2's
`px9_decomp` drew empty rooms, and why the newer px9 — whose bit cache stays
under 16 bits and so fits float32 exactly — could not run either.

**The API.** The shim implements PICO-8's verbs over the moy cart API —
`sin`/`cos` with their turn-and-flip semantics, the table verbs
(`add`/`del`/`foreach`/`all`/`count`) — `add` taking an INDEX, `del`
ANSWERING with what it removed, and a nil table a no-op in every one of them,
which is how `libryinth` deals a hand (`add(e.books, del(E, rnd(E)))`) and
fills a list it has not created yet — `btn`/`btnp` with PICO-8's auto-repeat,
the INVERTED fills (`poke(0x5f34, 2)` arms the mode and a colour's
`0x1800.0000` bits ask for it, and `circfill`/`rectfill` then paint the
COMPLEMENT of the shape — `gift guardian` frames its snow globes with one, and
drawn the ordinary way that is a solid disc over the art inside),
`pal()` in every form including the table form and the **screen palette**
(`pal(c, d, 1)`, kept across frames as PICO-8 keeps it -- and applied as pixels
are drawn, not to the finished frame, so a fade over a frame the cart does not
redraw stays put; SPEC.md 12.1), `palt()` as real
transparency state (so `palt(0, false)` draws black) -- and the DRAW palette
and its transparency persist across frames as PICO-8's do, which they did not
until 2026-09-14: the console resets a canvas's draw state after every cart
frame and only the screen palette was being put back, so a cart that set either
once in `_init` had it for exactly one frame. `gift guardian` marks pink
transparent with `palt(14, true)` and drew a pink block behind every snow globe
from the second frame on, in PLAY, where its title screen looked right --
`fillp()` with its
two-nibble colours and its transparency bit, `oval`/`ovalfill`, `rnd()`
including the table form, string indexing, coroutines (`cocreate`, `coresume`,
`costatus`, `yield`), and the PICO-8 system font at its true 3×5, drawn by the
console in C where the machine is open — with the P8SCII control codes carts
print with: wide and tall text, foreground and background colours, outlines
(`\^o`), cursor nudges, repeat, tab, invert, the cell size (`\^x`/`\^y`,
`0x5f59`), and the RAW MEMORY WRITES — `\^@addrnnnn` and `\^!addr` poke the
bytes that follow to an address, which is how a one-kilobyte cart carries its
sprite sheet in a string (`loom valley`).

**A cart's OWN font** (`0x5600`) is drawn, not merely remembered: eight
attribute bytes (cell width, the width past character 128, height, draw
offset), 120 bytes of per-character width adjustment and lift, then eight bytes
a glyph. `poke(0x5f58, 0x81)` turns it on for everything the cart prints and
`\014`/`\015` switch fonts mid-string, as they do there. `ruby eyes` sets its
whole game in one.

**`flip()` is a REAL frame boundary.** PICO-8 runs a cart's top level to
completion and only then starts calling `_update`/`_draw`, so a cart may simply
loop and present each frame itself — and a cart that does define an update may
still flip inside it, to type a letter a frame or to sit on `while not btnp(4)
do flip() end` until the reader presses a button. Neither is cosmetic: with
`flip()` a no-op the first hangs before the console sees a frame and the second
never returns. So a cart that flips runs its frame inside a COROUTINE the
console resumes once a tick, and `flip()` is the yield; a tick that stopped on
a flip has already presented its frame, and `_draw` is not called for it, as
PICO-8 does not. The porter reads off the source whether a cart flips at all —
one that does not never enters the coroutine and pays nothing — and hands a
looping cart's top level to `__p8_main` rather than running it where it stands.
`\^1`..`\^9` inside a printed string skips 1,2,4..256 frames and is the same
yield: `loom valley`'s whole flip-and-clear is `?"\^1\^c"`, IN THAT ORDER, so
a printer that drew the string and flipped afterwards would present the cleared
screen.

**`line()` remembers where it stopped**, which is PICO-8's line state: `line(x1,
y1)` continues a polyline from the end of the last line, `line()` with no
arguments makes the next call only MARK the end without drawing, and one
argument is the colour and a reset. Without it every segment of a polyline ran
back to (0, 0), and `loom valley` — which draws its whole terrain that way —
came out as noise.

Two things a PICO-8 native should know about colour here: the draw palette is
four bits, as it is there (VRAM holds a nibble), so `pal(c, 128 + i)` without
the third argument draws colour `i`, and a draw-palette byte with bit 7 set
marks that colour transparent, as bit 4 does; the secret sixteen come only
through the screen palette, `pal(c, 128 + i, 1)`.

**The machine.** `peek`/`poke`/`peek2`/`poke2`/`peek4`/`poke4`/`memcpy`/`memset`
address the real memory map; `sget`/`sset` and `mget`/`mset` read and write it;
`fget`/`fset` are the console's own flags; `reload`/`cstore` copy from and to a
ROM snapshot of the seeded image. A cart that bakes a texture by copying the
screen into the sheet, fades by `memcpy` into the palette, or draws a shadow by
`peek`/`poke` over `0x6000` does exactly that here.

Where the machine is open the shim's hot verbs are the console's C rather than
Lua closures: the whole memory set above, `all`/`foreach` and the table verbs,
the number verbs (`flr`, `abs`, `min`, `max`, `mid`, `sgn`, `sin`, `cos`,
`atan2`), `split`, `rnd`/`srand`, the 16.16 bit verbs,
`mget`/`mset`/`fget`/`fset`, `btn`/`btnp` with
their latch, the nine native bit operators above, and **every draw verb** —
`pset` `pget` `line` `rect` `rectfill` `circ` `circfill` `oval` `ovalfill`
`spr` `sspr` `map` `print` `camera` `color` `cursor` `pal` `palt` `fillp`
`sget` `sset`. Each is ONE binding call, with p8's coercions, the pen, the fill
pattern and the palettes resolved in C from the machine's own bytes — which is
why the draw state those verbs need lives in the memory map (the pen at
`0x5f25`, the print cursor at `0x5f26`, the fill pattern at `0x5f31`, the
screen palette at `0x5f10`), so `peek` and `poke` of those addresses agree with
the verbs and a `memcpy` fade into the screen palette survives the frame the
console resets draw state on. The shim aliases per verb and keeps its Lua for a
host that offers none of them; `cls` and `clip` are the console's own already
and were never wrapped; and `libmoy/test/p8lib.moy` sweeps every verb through
both lanes over seeded draw states — palette maps, transparency, fill patterns,
a camera, a clip, fractional and negative coordinates, nil arguments — and
holds them to one answer. `sqrt` and `ceil` stay Lua on purpose: both are
already bare aliases to `math`, so there is nothing to promote.

**`split` and the generator** are the two promotions that needed more than a
transcription of the verb. `split` is PICO-8's own — Lua's string library has
no twin — and it is what a ported cart's data tables are written in, one
`split"1,2,3,..."` per row; its ARITY is part of its input, because a data row
is a one-argument call and a parser call is a three-argument one, so the C
pins the stack before it pushes anything (a version that did not read the
subject as its own separator and answered empty strings, through every
three-argument test it had).

`rnd` and `srand` move TOGETHER or not at all, because they are one generator,
and moving a generator moves the random sequence a cart's world is built from
— so the C is not an equivalent generator but Lua's own xoshiro256**,
transcribed from `lmathlib.c` so a seeded cart lays out the level it always
laid out. `p8lib.moy` seeds both lanes alike and compares 20,000 draws from
each of eight seeds; a cart that never seeds still differs run to run, because
the machine draws its own starting words from lmathlib's state at open.

**The lookup-table span** is the one promotion where the C had to be able to
say *"not this one"* and still be the whole verb. `__p8_lut_span` is the fold
target for `for a=i,j do poke(a,peek(lut|peek(a))) end` (a lit room, a fade),
and the machine only takes three plain integers — Lua's numeric `for` coerces
its bounds and `|` refuses a non-integral float, and transcribing either rule
into C would be a second copy of something the shim already owns. So the verb
is bound through a FACTORY: `__moy_p8_lut_span(fallback)` returns the verb
carrying the shim's own loop as an upvalue, runs the span itself when it
recognises the arguments, and calls the loop when it does not. One definition
of the coercions, still in Lua, still the reference — and no Lua frame on the
three hundred calls a frame a lighting cart makes.

**`map` binds alone, and the camera stays the shim's.** The two used to move
together, which read as a rule about the pair but is really one-directional: a
C `camera()` with the shim's Lua `map()` in play leaves that loop clipping
against a copy nothing updates, while a C `map()` with the shim's `camera()`
needs nothing from the shim — it clips against the *console's* camera, which
is what `camera()` writes and is the more current of the two (a cart that pokes
`0x5f28` moves it; the Lua copy it would not). A host with its own native
masked walk takes it too: both walks are `moy_spr` per cell, so what the C
removes is the wrapper around them, not the walk.

**Tile 0 is empty**, whichever way the cell was written. A console cell holds
`tile+1` with `0` for empty and the importer maps p8's "sprite 0, empty by
convention" onto `0`; the runtime write path stored a `0` as cell `1`, so
`mset(x, y, 0)` — p8's only way to clear a cell — left one that drew sprite 0
where the seeded map drew nothing. `mget` and `peek` are unaffected either way,
which is why it stayed hidden.

## What is approximated

These convert, run, and do *something* — but not the thing PICO-8 did. The
verdict names them per cart.

| verb | what happens instead |
|---|---|
| `menuitem` | the pause menu is the console's; entries are not shown |
| `stat` | clock, CPU and audio counters read 0 |
| the mouse (`stat(32)`/`(33)`/`(34)`) | **real** — the console's own pointer, which is the glass on a board and a mouse on a desktop or in a browser. Enabled by `poke(0x5f2d, 1)` as it is there, latched once a tick beside the buttons. No wheel (`stat(36)` is 0) and no second or third button. **Where the mouse is when there is none:** p8 has no absent value for a cart to read — the machine always has a mouse somewhere — so "no pointer" is spelled as a position OFF THE SCREEN (−8, −8), which is what PICO-8 reports when the pointer leaves the 128×128 window and what a cart's own bounds guard is already written for. The position holds while there IS a pointer and through a released finger's linger, so a touch panel drags like a mouse; when the linger runs out it parks. A HOVERING source (desktop, browser) never expires and so never parks. That matters on glass, because a finger cannot be moved off the board the way a mouse can: `dungeons & diagrams` re-asserts its board cursor from the mouse every frame, *after* its own buttons have moved it, so a pointer that never leaves is a d-pad that never works again. Driven on a T-Deck 2026-09-12: a screen-centre touch reaches the cart as 66,66 of its own 128×128, the button reads 1 through a drag and 0 on release |
| the frame cadence | the host's, not the shim's (§5): one tick per PICO-8 period on the host's clock, with the host's catch-up rule (extra ticks only while a tick costs under half the period, PICO-8's own line for two ticks per draw; past it a late frame slows time, as on PICO-8). `_draw` never runs before the first `_update`. A 60 fps cart on a host drawing 30 runs two ticks per draw, PICO-8's degraded mode, not something to improve on |
| sfx/music memory (`0x3100`–`0x42ff`) | remembered, not played; the imported sounds play |
| `sfx(n, ch, offset, len)` | the whole sound plays |
| `cstore` | writes the ROM snapshot in memory; nothing reaches the cart file |
| `0x5f2c` screen modes | the 64×64 and rotated modes are refused; the normal mode is a no-op |
| bitplane masks (`0x5f5e`), sheet/screen remaps (`0x5f54`/`0x5f55`) | remembered, not applied |
| `ovalfill` with the inversion bits | draws the ordinary oval. `circfill` and `rectfill` invert; `ovalfill` does not, because `moy_ellipse` walks its spans with Bresenham and a second copy of that walk is how the two would drift into a seam. No corpus cart asks for it |
| 16.16 arithmetic | the bit verbs (`band`, `shr`, `rotl`, …) work on the 32-bit fixed image, and a hex literal spells PICO-8's bit pattern (`0xffff` is −1, `0x0.0001` is 1/65536) — exact whenever the pattern fits float32's 24 bits, which fraction-packed flags and masks do. A data decoder that packs its cache into a full 32-bit word does not run — 31 significant bits do not fit 24; one that reads a byte at a time (the newer px9) does |
| `cartdata` `dget` `dset` | **real** — they persist through the console's own save memory |
| `import` `export` `folder` `info` `ls` | PICO-8's console commands are callable from cart code and carts keep the one that built them — `octosnatch` still imports "art.png" from `_init`. There is no editor and no filesystem behind a game here, and the cart's art is already in it, so they do what the BBS player does with them: nothing |
| `printh` `extcmd` `holdframe` | dropped. `holdframe` asks PICO-8 to hold the next flip until the frame is up, which is what the console's own pacing already does |

## What cannot come across

| verb | why |
|---|---|
| `load` | the launcher swaps carts here; a multi-cart game is refused |
| `reboot` `stop` | there is no command line to drop to |
| `trace` `info` `serial` | no traceback to fetch, no console to print to, nothing on the other end of the port |
| `#include` | the included file does not travel with the cart. A moy cart can hold several scripts (SPEC.md 4), but `#include` splices TEXT into one scope and these are separate chunks, so a resolved include would still have to be pasted rather than listed |

## The test corpus

Sixteen carts, chosen to stress *different* things rather than to be a top
sixteen: a raycaster, a world-gen sim, a minified bytecode VM, carts whose
graphics live in packed strings. The last four came off PICO-8's own front
page on 2026-09-12 and each earned its place by being the only cart here that
reached a particular dialect bug. They are not in this repository — see
[`conformance/p8_corpus.json`](conformance/p8_corpus.json) for the links;
`conformance/p8_corpus.py` lists the ones a directory lacks, to download by
hand (nothing here fetches from the BBS, CI included). `make -C libmoy
p8-carts` runs the gate on what you have downloaded.

**The gate is weak on purpose and you should not read it as "plays" — and
least of all as "plays on a board".** Two of the carts below pass every column
here and then hang a T-Deck until it is reset over USB, which is why moybyte's
fleet shelf (`tools/gen_p8_ports.py`) takes a run on glass and not a green row
as its bar. It
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
| picooffroad | runs | yes | yes | yes | **plays** — races, with its shadow and its fades, on the reference boards |
| petal_quest | runs | yes | yes | yes | **plays** from the title into its coroutine cutscenes, with its map |
| dungeons_and_diagrams | gaps | yes | yes | yes | **plays**; its packed-flag bit trick reads right now (16.16 bit verbs), and it is the corpus cart that asks for the MOUSE — a puzzle whose natural input is pointing at a cell, on boards that all have a touchscreen |
| mossmoss | gaps | yes | yes | yes | **plays**; slows at its later levels on the S3 boards |
| lowmemsky | gaps | yes | yes | yes | **plays**; it reads its buttons as `btn"1"`, the size-coder's string form, which both lanes coerce as PICO-8 does |
| dank_tomb | gaps | yes | yes | yes | **plays**; its lighting loop is one `__moy_lut_span` |
| 42930 (*Charge!*) | runs | yes | yes | yes | *(frames only)* — 105 `//` comments, every one of which used to convert to a division |
| deepdark | runs | yes | yes | yes | *(frames only)* — its torch-lit room scrolls; it keeps that scroll in a global called `camera`. **WEDGES A BOARD**: it passes this gate and then hangs a T-Deck hard enough that the dev channel stops answering (2026-09-14), so it is imported and studied here and is not on the fleet's shelf |
| giftguardian | runs | yes | yes | no | *(frames only)* — title, iris wipe, then the game; its `?` prints a long string that closes on the next line |
| loop | gaps | yes | yes | yes | *(frames only)* — reaches its menu; its button tables are named `p1➡️`, `p1⬆️`, one identifier each. **WEDGES A BOARD**, like deepdark and for the same unmeasured reason: the gate asks whether a desktop's frame changed inside 45 s, which is not the question a 60 fps cart on an S3 answers |
| terra_1cart | gaps | no | no | no | *(not played — generates its world past the harness's 45 s)* |
| celeste_classic_2 | refused | yes | yes | yes | starts; nothing moves, only the clouds draw — its levels are px9-packed 16.16 |
| nimudazus | refused | no | no | no | *(not played — errors decoding its bytecode)* |
| poom | refused | yes | yes | no | multi-cart; the loading screen draws through the memory map and stops there |

Fourteen of sixteen boot, three are refused up front and two of those would
have sat on a shelf looking broken. Of the thirteen that import, one the
verdict calls "gaps" still fails — on time, not on a verb — which is the
honest edge of a static reading. If you convert a cart and play it, the useful
contribution is a line in this table.

**What a gate that compares us to OURSELVES cannot see (2026-09-14).** The
owner played `gift guardian` on a board and on real PICO-8 and the two were not
the same cart: every snow globe was a flat disc here and a glass globe with a
house, a candy cane or a reindeer inside there. Nothing caught it, and the
reason is structural — the corpus gate runs a cart under `run_cart`, which is
*this* importer's player, so a verb we get wrong we get wrong identically in
both places and the frames agree. Three separate checks that afternoon compared
a board against `run_cart` and all three said "correct".

The cart draws those globes with `circfill(x, y, r, invert + 6)` after
`poke(0x5f34, 0x2)`, which is PICO-8's inverted fill: the circle frames the
globe instead of filling it. We drew the disc. It is implemented now
(`moy_p8.c`, the shim, both lanes held to one answer in `libmoy/test/p8lib.moy`)
— but the lesson is the gate's, not the verb's: **a screenshot of real PICO-8 is
the only reference this repository does not already own.**

**Where the bugs actually were (2026-09-12).** The eighteen carts on PICO-8's
front page were run through this as a sweep, and twelve booted. Five of the
six failures were not a missing verb or a machine this console lacks: they
were the porter handing Lua something the cart had not written — `//` read as
a division, a glyph split out of the middle of a name, `if cond do` skipped
because the line opened on a closing paren, a `?`'s paren landed inside a long
string, and `T[2].ready << 1` rewritten as `T[2].__p8_shl(ready, 1)`. Three of
those five produce output that PARSES, which is why none of them had been
found by a corpus of carts that ran. Sixteen of eighteen boot now; the two
that do not are the two the verdict refuses up front, both multi-cart.

The sweep also found two that no cart FAILS on, because both answer: `\`
taking the primary beside it rather than the product (above), and `add`/`del`
answering differently from PICO-8's. A cart is a poor detector of a wrong
answer — which is what `libmoy/test/p8lib.moy` and
`libmoy/test/p8_port_check.py` are for, and where each of these now has a
case.

## Performance on the reference boards — a dated snapshot

The living ledger is moybyte's issue #66; this is the state on 2026-09-03, the
carts imported with `--zoom`, WiFi off, medians of a scripted run (title · play
fps). The S3 boards hold 30 fps on four of the eight, sit just under on mossmoss
and dank_tomb, and fall to 15–20 in play on the two draw-bound ones,
picooffroad and crimson_night:

| cart (rate) | ESP32-P4 | T-Deck (S3) | Guition (S3) |
|---|---|---|---|
| petal_quest (60) | 63 · 63 | 53 · 57 | 61 · 62 |
| mossmoss (30) | 30 · 28 | 26 · 25 | 25 · 23 |
| dank_tomb (60) | 35 · 35 | 21 · 24 | 26 · 26 |
| picooffroad (30) | 62 · 30 | 32 · 15 | 36 · 19 |
| bunnysurvivor (60) | 61 · 62 | 49 · 40 | 54 · 50 |
| crimson_night (60) | 63 · 38 | 26 · 16 | 62 · 20 |
| dungeons_and_diagrams (60) | 63 · 63 | 59 · 58 | 63 · 61 |
| lowmemsky (60) | 62 · 62 | 41 · 43 | 56 · 53 |

Where the S3 frame goes for a 30 fps cart like mossmoss: ~27 ms is the cart's
own Lua (its entity loops; the shim is under a fifth of it), ~6 ms the console's
composite and chrome, ~4 ms its input and loop. Which levers paid and which did
not is #66's; what is left is structural.

A cart that plays on the host and fails only on a board, only sometimes, is
usually the frame cadence the replayer cannot reproduce (`run_cart --dt`), not
the architecture: dank_tomb's "nil position at init" was a draw before the
first update, back when the shim kept the clock.

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
