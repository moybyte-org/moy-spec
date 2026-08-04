# moycore

The moy console as a library: the raster, the palette, the font, the sprite
sheet and tilemap, the cart format, and the verb table. Pure Python, stdlib
only, no dependencies, imports on MicroPython.

It exists for three reasons.

**A spec whose only implementation is a 788 KB `.wasm` is not checkable.**
SPEC.md says implementations render "pixel-identically" and calls `verbs.moy`
the seed of a conformance suite; until now a third implementer had nothing to
diff against. `canvas.py` is the readable answer to "what exactly does
`circ(cx, cy, r, c)` light up", which prose cannot be.

**Embedding should be cheaper than reimplementing.** A host supplies pixels out,
buttons in, and a Lua VM. Everything between is here.

**The conformance suite has to run against something.** It runs against this.

## What is here

| file | |
|---|---|
| `canvas.py` | the 320×240 indexed raster and every SPEC.md 6 / 7.1 / 7.2 verb |
| `palette.py` | the 64-entry table, loaded from the normative `palette.json` |
| `font.py` | the 8×8 font, loaded from the normative `font.bin` |
| `sheet.py` | `SpriteSheet` (`.moygfx`) and `TileMap` (`.moymap`) |
| `cart.py` | the cart folder: manifest, script, assets, and what refuses vs degrades |
| `api.py` | the verb table, input model, `pmem` |
| `check.py` | the static checks behind `moy.py check` |
| `budget.py` | SPEC.md 1.1's memory floor, as numbers a tool can use |
| `pack.py` | the single-file shipping form (a proposal — see `proposals/`) |
| `png.py` | a minimal PNG codec for goldens and asset conversion |

`palette.json` and `font.bin` are **not** copied in here. They are normative
data that lives beside SPEC.md, and moycore reads them, so there is no second
copy to drift.

## Embedding

```python
import moycore

canvas = moycore.Canvas()                       # 320x240, one byte per pixel
cart   = moycore.load_cart("mygame.moy")
inp    = moycore.Input(players=1)
api    = moycore.make_api(canvas, cart, inp)    # {name: callable}

# your frame loop
inp.set_held({"left", "a"})                     # from your own hardware
inp.tick()
canvas.reset_state()                            # draw state is per-frame
api["cls"](1); api["spr"](3, 100, 100)          # or hand `api` to a Lua VM
your_display.blit(canvas.to_rgb565())
```

`make_api` returns a plain dict because **the language binding is a seam**.
moycore does not embed a Lua VM and does not want to: SPEC.md 4 says a cart is
Lua 5.4, and which Lua that is — a C VM, a MicroPython usermod, a browser build
— is a host's decision. A Lua host installs the dict as globals; the
conformance raster suite calls it directly.

## What is deliberately absent

No launcher, no windowing, no editors, no drivers, no filesystem access, no
audio synthesis backend. SPEC.md 0 puts all of that permanently out of scope for
a *cart*, and it is exactly where consoles differ and should keep differing.

No sprite batching, tilemap caching, sub-rect viewports or partial-frame
restore, either. Those are real host performance work and the reference console
does all of them — but they are invisible to a cart, and a reader trying to
learn the raster should not have to step around them. A host that adds them owes
one thing: the same pixels this produces.

## Provenance and verification

moycore was extracted from the reference implementation
([moybyte](https://github.com/moybyte-org/moybyte)), so "it draws the same
pixels" is a claim about a refactor — and a refactor can be checked rather than
asserted:

```
python3 conformance/parity.py --ref /path/to/moybyte
```

replays every conformance scene through both rasterizers and compares the
framebuffers byte for byte. All 8 scenes are currently identical.

## Portability rules

Anything added here must import on MicroPython: stdlib only, no f-strings, no
dataclasses, no `typing`, no comprehension-heavy hot paths, no `os.path`.
