# Proposal: the PICO-8 / TIC-80 verb gaps — what a native of those consoles misses here

**Status: draft. Not part of core 0.1.** Nothing in this file changes SPEC.md;
it is the gap analysis of 2026-08-12, grounded against SPEC.md's actual verb
tables, the p8 port shim's stub list (every stub is a confessed gap), and the
reference console's shipped Lua sandbox — written down so each item gets a
deliberate yes/no instead of drifting in as "obviously we should".

## Who this serves, precisely

Two audiences, and only one of them needs spec verbs:

- **Ports** don't. The p8 shim already translates the whole PICO-8 surface a
  ported cart touches; where a host offers a fast lane (moybyte's native
  masked-map walk) the shim probes for it and falls back. Ports are served.
- **People writing NEW carts with p8/TIC-80 muscle memory** are the audience
  this spec courts, and they hit the gaps bare: no `fget` for collision tags,
  no `srand` for a daily-seed game, no coroutines for a cutscene. Every one of
  those is a small "this console is less than the one I came from" moment at
  exactly the point where adoption is decided.

The pattern worth noticing up front: the three biggest wins are nearly free,
because they are sandbox or spec-text changes, not raster work.

## Tier 1 — cheap, high-value, recommended

### 1. `coroutine` enters the sandbox (§4.1 amendment)

Both source consoles have it and p8 natives use it *idiomatically* —
`cocreate`/`coresume` is how cutscenes, staged animations and async game
logic are written there. §4.1 excludes it today, and §4.1's own rule ("a
maximum, not a suggestion — a host that exposes more accumulates carts that
run nowhere else") is exactly why this must be a SPEC amendment and not a
host patch: every host moves together or none does.

The case for admission: `coroutine` is pure VM — no I/O, no clock, no
allocation surface beyond what `table` already grants, and no conformance
hazard (its behavior is Lua 5.4's, which §4 already pins). The cost is one
`luaL_requiref` per host and a conformance scene that yields across frames.
Nothing else in the excluded set (`io`, `os`, `debug`, `package`) shares
this property; admitting coroutine does not crack the door for them.

### 2. `srand(seed)`

`rnd(n)` exists; seeding does not. Without it there are no deterministic
replays, no daily-seed games, no reproducible bug reports for anything using
randomness. Both source consoles have it (p8 `srand`, TIC-80 seeds via
`math.randomseed` which our sandbox admits but §9 does not bless). One verb,
one line of spec, one conformance scene (same seed → same first N draws).

### 3. Bless the pixel READ form: `pix(x, y) -> c`

p8's `pget` / TIC-80's `pix(x, y)` read form. The reference console already
answers it — but SPEC.md §6 documents only the 3-arg set form, so the read
is host folklore, uncovered by conformance, and a port of any `pget`-using
cart silently depends on it. Cheapest item here: this is spec'ing existing
behavior, not building anything. (Same class, smaller: `mouse()` exists on
the reference console and is absent from §7.3 — document or deprecate.)

## Tier 2 — the flags bundle (the one that needs real design)

**`fget(n [, bit])` / `fset(n, bit, on)` + a `layers` mask argument on
`map()`** — the fantasy-console idiom for tagging sprites solid/spike/coin
and drawing map strata by tag. Both consoles have it; kids ported FROM those
consoles reach for it on day one, and today's answer ("keep flags in your own
table") is the conversion checklist's least-loved line.

What makes this a bundle rather than a verb:

- **A format home.** Flags are 256 bytes of per-sprite data with nowhere to
  live — the p8 shim bakes them into the cart source as hex. Options, in
  rough order of appeal: a fourth optional cart file (`flags.bin`, 256
  bytes, absent = all-zero); a field in `manifest.json` (hex string — ugly
  past 64 sprites); an extension block in `sprites.moygfx` (couples two
  concerns). The sidecar file matches §3's one-concern-per-file shape.
- **An editor surface.** A spec verb kids can't author for is port-only
  machinery in spec clothing. The classic answer is 8 toggle dots in the
  sprite editor's inspector row.
- **Semantics already exist, pinned.** The reference console ships the exact
  masked-map walk as a host extension (`__moy_map_masked`/`__moy_map_flags`,
  probed nil-safe by the p8 shim — the `view()` pattern), byte-exact against
  the naive per-cell loop across a 12-scene A/B matrix. p8's rules carried
  over: tile 0 never draws; `layers == 0` or absent means no filter;
  otherwise a cell draws when `(flags[tile] & layers) ~= 0`.

Graduation path: enter `fget`/`fset`/`map(..., layers)` through the
provisional tier (the §6.1 mechanism — conformance-scened but not counted in
core), with the sidecar file as its format rider. If it earns its keep, it
graduates with the tier's usual evidence.

## Tier 3 — worth pricing, not urgent

| item | who | note |
|---|---|---|
| `fillp(p)` pattern fills | p8 | The dithering staple; the p8 aesthetic crowd uses it constantly. A pattern word in draw state honoured by the fill verbs — libmoy-shaped, conformance-scene-able. The largest raster item on this list. |
| `sget(x, y)` / `sset(x, y, c)` | p8 | Runtime sheet-pixel access (art-as-data, generated sprites). Cheap: the sheet is indexed bytes. Interacts with live sprite editing (gen counters) — needs a paragraph, not a design. |
| `oval` / `ovalfill` | both | Ellipses. Easy kernel, mild demand. |
| `music(n, fade_ms)` / `sfx(n, ch, offset, len)` | p8 | Fade-out is common polish; offset/length are instrument tricks. Upstream libmoy audio work; §8.3's conformance exemption means no golden pressure. |
| `trace(msg)` | TIC-80 | Debug print to the host console — pure DX, lovely on the wasm runner. Host-extension shaped (the `view()` pattern); may never need to be core. |
| `ttri` (textured triangle) | TIC-80 | The real-3D staple past `tline`. **Blocked on procedure:** §6.1 declares the provisional tier's membership settled, so this reopens that decision explicitly or waits for the tier to graduate. |

## By design, never — written down so they stop being re-asked

- **`peek`/`poke`/`memcpy`/`memset`** — there is no memory-mapped hardware
  model and there never will be; it is the one permanent hole in p8 porting,
  and papering over it with a fake address space would be a lie that
  conformance can't cover.
- **`flip()`** — §5's tick model owns cadence; a busy-loop cart is a ported
  cart, and the shim's frame-quantized pacing is the answer.
- **`menuitem`** — the console owns its menus (and its exit gesture).
- **`stat()`** — a grab-bag by design; moy answers each real question with a
  real verb (`time`, `players`, `touch`), and the perf HUD belongs to hosts.
- **`vbank`/`sync`** — the reference console's layer verbs cover the use;
  a second VRAM model is a second compositor contract.
- **custom `font`** — §6 pins the 8×8 font for conformance; a cart wanting
  its own letters draws them from its sheet, which is also how p8 carts
  actually do it.

## Recommended order

1. Tier 1 as one spec revision: §4.1 admits `coroutine`, §9 gains `srand`,
   §6 documents the `pix` read form (+ §7.3 decides `mouse()`) — each with
   its conformance scene, every host updated in the same change.
2. The flags bundle as its own provisional-tier proposal, sidecar format
   included, once an editor surface is sketched.
3. Tier 3 items individually, on demand, `fillp` first if the p8 crowd
   materializes.
