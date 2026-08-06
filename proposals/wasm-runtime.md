# Proposal: `runtime: "wasm"` — the compiled-cart binding

**Status: draft. Not part of core 0.1.** SPEC.md §15 records the doctrine; this
document is the ABI it points at. Every number in it is measured, not estimated —
the evidence run is a 6502 interpreter core, line-faithful in Lua and C with
identical cycle counts out of every runtime, on the reference console's RISC-V
board at its shipping clock (moybyte#158, `experiments/wasm_aot`, 2026-07-27).
Nothing here is normative until the open items at the end are closed.

## Why a second binding, and why this one

The verb table is the console (SPEC.md §15); Lua is its first binding, not its
definition. The second binding exists for the work the first cannot hold:
**step-bounded** rendering — voxel terrain, general textured 3D, per-pixel
effects, emulators — where the cost is the cart's own loop and no verb can absorb
it (SPEC.md §6.1).

A native binary cannot be that binding. The reference lineup alone is already
three instruction sets (Xtensa, RISC-V, x86-64/ARM host), so "compiled cart"
would mean per-board artifacts — the fragmentation every small-console ecosystem
drowns in. WebAssembly is the compilation target every systems language shares,
it is sandboxed by construction (linear memory is bounded; imports are the *only*
capability surface — the verb table literally is the sandbox), and it is one
artifact for every tier including the browser.

**The measured case** (reference hardware, on glass):

| runtime | 6502 instr/s | vs Lua | arithmetic (`spin`) |
|---|---|---|---|
| Lua (the shipping binding) | 0.173 M | 1.0× | 5.2 M ops/s |
| WASM, WAMR fast-interp | 0.188 M | **1.09×** | 12.35 M |
| WASM, AOT (XIP — the *pessimistic* mode) | 2.828 M | **16.3×** | 476 M (**91×**) |

Two conclusions, both load-bearing: **interpreted WASM does not justify a
runtime** — its advantage collapses exactly on dispatch-shaped code, which is
what interpreters and emulators are — and **AOT does**. An interp-only evaluation
would have said no and been wrong.

## The cart

```json
{ "format": "moy-1", "title": "…", "runtime": "wasm", "main": "main.wasm" }
```

Everything else in the folder is unchanged: `sprites.moygfx`, `map.moymap`,
`sfx.moysfx`, the manifest fields of §3.1. A host that does not implement the
binding refuses the cart cleanly (§3.1); one that does loads `main.wasm` and
nothing else — **the `.wasm` is the sole portable artifact**. `.aot` files are
per-architecture build products and never appear in a cart.

Source is welcome beside it — `src/` in the folder, or a `"source"` manifest
field carrying a URL — and never required or verified. The always-readable tier
is the Lua cart.

## Module shape

- **Profile: wasm32, MVP.** No WASI, no threads, no SIMD, no GC proposal. One
  linear memory, exported as `memory`. The profile is pinned so a 2026 toolchain
  and a 2030 one produce carts the same host runs; extensions to it are a spec
  revision, not a toolchain default.
- **Exports:** `_init()`, `_update(f32 dt)`, `_draw()` — the §5 tick, exactly as
  the Lua binding calls them. `memory`. Nothing else is required.
- **Imports: module `"moy"`,** one import per verb, same names and §6/§7/§8/§9
  semantics as the Lua binding, with `i32` for integers and indices and `f32`
  where the Lua verb takes a fraction. The Lua build is `LUA_32BITS` (§4.2), so
  the two bindings already share a numeric world; nothing widens.
- **No other imports exist.** That sentence is the entire §4.1 sandbox for this
  binding.

A cart author's toolchain is one command, no SDK:

```sh
clang --target=wasm32 -O2 -nostdlib -Wl,--no-entry \
      -Wl,--export=_init,--export=_update,--export=_draw \
      -o main.wasm main.c
```

with a ~50-line `moy_cart.h` of import declarations
(`__attribute__((import_module("moy"), import_name("cls")))` …) that belongs in
this repository once the ABI freezes. `zig build-exe -target wasm32-freestanding`
and Rust's `wasm32-unknown-unknown` produce the same module with zero setup.

## The framebuffer contract — the new verbs

The measured blocker is not speed but the boundary: a compiled cart reaching
pixels through the `pix` import pays a trampoline per pixel — 76,800 crossings
per frame, dead at any VM speed. The fix is an import that hands over a whole
frame at once:

```c
void blit(i32 ptr, i32 pal_ptr);   /* ptr: 76,800 bytes in linear memory, one
                                      palette index per pixel, row-major
                                      320 × 240. pal_ptr: 0, or 192 bytes of
                                      RGB — a 64-entry palette presented with
                                      THIS frame */
```

Called at most once per `_draw`. The host validates the ranges, resolves the
indices through the frame's palette (`pal_ptr` if given, else the cart's §2.2
palette, else the default), and treats the result exactly as a §6-drawn frame.
A cart may freely mix `blit` with ordinary verbs; draw order is call order.

**The per-frame palette is deliberate, and it does not reopen §12.1.** That
decision forbids retroactively re-meaning pixels already drawn on a retained
canvas; a `blit` is a complete frame delivered together with its own palette —
nothing is retained, nothing re-meant, and the host's cost is rebuilding a
64-entry LUT per frame, which is noise. What it buys is the entire class of
runtime-palette work the fixed §2.2 table cannot express: palette-driven fades
and flashes, palette cycling (plasma, waterfalls), and — the case that surfaced
it — emulation. An emulated console's palette RAM changes at runtime; with a
per-frame palette, any game holding ≤ 64 simultaneous colors maps exactly,
fades included. (The NES needs none of this: its 54-entry master palette is
fixed hardware and fits §2.2 as-is. The GB's 4 shades likewise. Per-scanline
palettes remain a bridge deliberately not crossed; above 64 simultaneous, see
`blit565` below.)

Measured budget: ~4.6 M pixel-writes/s from AOT code into linear memory against
476 M ops/s of arithmetic — a full-screen software raster lands ~17 ms on the
measured board, inside a 30 fps frame with the geometry effectively free. This
does not reopen §12.6: the cart writes *its own* memory, the host's framebuffer
stays opaque, and hosts keep every freedom of depth, scale and byte order.

Assets stay host-side (`spr`, `map`, `sspr` render as ever). A later revision may
add read-only asset access into linear memory (`sheet_read(ptr)`-shaped) if a
ported engine demonstrates the need; it is deliberately absent until one does.

### Full colour — `blit565`, and why it is not the default

64 colors is a palette ceiling, not a hardware one, and it is the wrong ceiling
for a tier whose reason to exist is ports and commercial work. Content that was
never palettized — gradients, shaded 3D, photographic art — cannot be submitted
through `blit` without the cart quantizing or dithering it first. So a second
submission format, alongside the first, never replacing it:

```c
void blit565(i32 ptr);   /* ptr: 153,600 bytes in linear memory, RGB565
                            LITTLE-ENDIAN, row-major 320 × 240 */
```

Same rules as `blit`: at most once per `_draw`, host validates the range, the
result is treated exactly as a §6-drawn frame, freely mixed with ordinary verbs
in call order.

**The byte order is fixed by this document, and is not "whatever the panel
wants."** That is the whole difference between a portable contract and a device
one — the moment the submitted layout tracks the display, a cart writes to
*that* framebuffer rather than *a* framebuffer and §12.6 is quietly reopened. A
host with a byte-swapped 16-bit panel swaps; a browser expands to RGBA8888; a
desktop player expands to RGB888. Those conversions are dependency-free
streaming loops and run at roughly copy speed, which is what makes fixing the
order affordable rather than pious. Pinning it also keeps this tier
golden-checkable: a `blit565` frame hashes as deterministically as an indexed
one, so §11 conformance reaches compiled carts without a second mechanism.

**Do not reach for it expecting speed. It is slower on both sides of the
boundary.** Measured on an ESP32-P4 (360 MHz, PSRAM 200 MHz, 256 KB L2, `-O2`),
one rasterizer compiled twice from a single source, differing only in stored
pixel type:

| the cart's own raster | 8-bit indices | RGB565 |
|---|---|---|
| filled rects | 988 µs | 1292 µs (**+31%**) |
| textured scanlines | 6780 µs | 7455 µs (+10%) |
| scaled sprite columns | 7921 µs | 8518 µs (+7.5%) |
| triangles | 4789 µs | 5004 µs (+4.5%) |

Two bytes per pixel is twice the store traffic, and a software rasterizer is
store-bound. Against the ~17 ms full-screen budget above, choosing `blit565`
costs the cart **+0.8 to +5.3 ms** — and it saves the host only ~0.8 ms, the
difference between resolving a palette (1148 µs with a pixel-pair LUT; 2026 µs
with the per-pixel loop both current implementations still use) and copying
153,600 bytes (344 µs). Best case a wash, worst case six times worse. The
palette resolve does not close that gap with more optimization either: every
lookup's address depends on the byte just loaded, so it plateaus around 3× a
copy where a copy has no dependency chain at all.

**On the floor board it is not close.** Same bench, ESP32-S3 at 240 MHz with
octal PSRAM and no L2 — the board a cart is most likely to be too slow on, and
therefore the one that decides:

| the cart's own raster | 8-bit indices | RGB565 |
|---|---|---|
| filled rects | 3226 µs | 10615 µs (**3.3×**) |
| triangles | 9410 µs | 21853 µs (**2.3×**) |
| scaled sprite columns | 18466 µs | 25163 µs (1.4×) |
| textured scanlines | 18275 µs | 20823 µs (1.1×) |

A 32-bit fill store covers four indexed pixels and only two RGB565 ones, and
with no cache to absorb it the wider format is paid in full. The host side
inverts too: with the source half the size, the palette resolve is **cheaper
than the copy it would replace** — 1681 µs against 2483 µs into the panel's
bounce buffer. So on this board `blit565` costs the cart up to 3.3× and saves
the host nothing at all.

The rule that follows: **a cart that could have been indexed should stay
indexed.** `blit565` is for carts whose pixels are inherently direct-color,
where the indexed route would cost a quantization pass rather than save a store.
On the faster board that rule is advice; on the floor board it is close to a
requirement, and a cart that ignores it will be judged on the floor board.

(Floor-board figures are at 80 MHz PSRAM, not the 120 MHz the reference console
ships: that board's flash is not verified for the high-performance mode
`SPIRAM_SPEED_120M` requires, and a 120 MHz build aborts in MSPI timing init.
80 MHz makes external memory dearer than it really is, so the margins above are
generous — but the 3.3× is far outside what a bus-speed correction reaches, and
the internal-SRAM rows do not depend on it at all.)

**Memory.** 153,600 bytes against §1.1's 192 KB cart heap leaves ~40 KB for the
game, which is not a budget. On the floor board it is worse than a budget
problem: with the console's own 76,800-byte canvas resident, a second
153,600-byte buffer **could not be allocated contiguously in internal SRAM at
all** — on an otherwise empty heap, before MicroPython, the Lua allocator's
48 KB floor or the DMA buffers exist. A `blit565` cart there is committed to
external memory for its framebuffer, which is exactly where the 3.3× above
comes from. §1.1's ≈400 KB is a **tier-1 floor**: it exists so
the script tier stays implementable on modest hardware, and it is stated in
terms of a host that owns every pixel. This tier owns none of that — a host
implementing it already carries a WASM runtime, an AOT toolchain, and on the
reference RISC-V board a dedicated XIP flash partition. Nothing that can do
those things is short of RAM. **The compiled tier therefore declares its own
floor** rather than bending tier 1's, and `blit565`'s framebuffer is the reason
the number has to move. Sizing it is open item 8.

## PCM audio — the hardware tier's second gap

SPEC.md §8 is a tracker-shaped data model, which is right for authored carts and
useless for an emulated APU or a ported engine's mixer: those produce a sample
stream. The binding wants one import:

```c
i32 snd(i32 ptr, i32 nframes);   /* nframes of signed 16-bit mono (or LR
                                    interleaved stereo; TBD with the first
                                    implementation) at a host-declared rate.
                                    Returns frames accepted -- a full return
                                    means keep feeding, 0 means the host's
                                    buffer is full this tick */
```

§8.3 already makes silence a valid rendering, so a host without audio hardware
accepts and drops — the cart cannot tell, exactly as with `sfx`. Rate, channel
count and buffer depth get pinned by the first implementation, not guessed
here; what is decided now is only that the compiled tier's audio surface is
**samples, not the §8 data model** — the same finding as the framebuffer and
the per-frame palette, from a third angle: this tier programs the console's
hardware, not the script tier's abstractions.

## Determinism

WASM is deterministic except NaN bit patterns. The binding pins it with one rule:
**a conforming host may canonicalize NaNs; a conforming cart must not depend on
NaN payloads.** Everything else — integer arithmetic, `f32` rounding, linear
memory — is bit-identical across engines by the WASM spec itself, which makes
this binding *easier* to hold to golden frames than Lua was: the frame a cart
blits is the frame the suite diffs, on every host.

## Distribution and AOT — host policy, not cart contract

How a host executes the `.wasm` is its own business, exactly as PSRAM placement
is (§1.1). The measured realities, recorded so ports plan for them:

- **Browser, desktop:** JIT the `.wasm` directly. No install step, and the
  browser is the fastest tier. A future web runner instantiates the cart as a
  sibling module with imports bound to the console's verbs — never a WASM
  interpreter nested inside a WASM console.
- **Reference RISC-V board:** zero exec-capable heap — AOT text must be XIP-mapped
  from its own flash partition. Installing a compiled cart writes that partition
  (flash wear, per-install). The measured 16× *is* this slower XIP mode; plain
  AOT would be faster and cannot load there at all.
- **Xtensa board:** untested. It may have exec heap and skip XIP entirely — the
  first open item below.
- **Store fan-out:** a store may serve pre-compiled `.aot` variants per
  architecture alongside the canonical `.wasm`. `wamrc` ships prebuilt; runtime
  and compiler versions must match (the evidence run pins WAMR 2.4.5).

Integration frictions already catalogued by the evidence run, so the next
implementer inherits them: WAMR's `LIBC_WASI` defaults on and fails riscv32
builds; `REF_TYPES` defaults differ between its linux and esp-idf paths; a
`br_table`-heavy module loads on linux and is rejected by the esp-idf build
(dispatch through a function-pointer table instead); WAMR must run on a real
pthread under ESP-IDF.

## What Lua carts get from this: nothing, deliberately

There is no Lua→AOT path. The 16× comes from static types, not from WASM — the
1.09× interpreter is the control group — and honest Lua→C transpilation measures
in the 1.2–2× range elsewhere. A Lua cart that outgrows its budget is *ported*:
same verbs, same tick, same assets, and the twin-cart pattern the reference
implementation already uses (line-faithful Lua/Python pairs held bit-identical by
a parity harness) extends to a C twin checked by the same golden frames. A typed
Lua dialect (Pallene, Nelua) compiling into this pipeline is plausible and
unproposed.

An engine-shaped cart may embed its *own* interpreter — vendored Lua compiles to
wasm32 — running gameplay scripts inside a compiled engine. That needs nothing
from this spec.

## Open items — in order, none skippable

1. **Xtensa AOT on the floor board** — same prebuilt `wamrc`,
   `--target=xtensa`. Decides whether the slower board is in scope and whether it
   skips the XIP install entirely.
2. **Build `blit`** and measure the real full-frame cost through the console's
   frame loop, not a bare harness. `blit565` rides the same item — the two
   differ only in whether the host resolves a palette or copies.
3. **One integrated cart** — the flat-shaded raycaster in C is the natural twin,
   since its Lua sibling is already measured on glass.
4. **A wasm twin of one conformance scene** passing the existing goldens — the
   moment this binding becomes testable rather than argued.
5. **`moy_cart.h`** committed here once the import list survives item 3.
6. **User-file access** (moybyte#108) is orthogonal but blocks the e-reader class
   of ports either way; the WASI-subset question belongs to that issue, not this
   one.
7. ~~**The `blit565` penalty on the floor board.**~~ **Measured 2026-08-06**, and
   the prediction held with room to spare: the cart-side cost widened from
   +4.5–31 % to **1.1–3.3×**, and the host-side saving did not merely narrow, it
   went negative — the palette resolve is *cheaper* than the copy `blit565`
   would substitute for. Both boards' figures are in the section above. What
   remains open is only the bus speed: the floor-board run is at 80 MHz PSRAM
   because that board's flash is not verified for the high-performance mode
   `SPIRAM_SPEED_120M` needs. A 120 MHz rerun on verified flash would shrink the
   PSRAM-resident margins; it cannot reach the internal-SRAM rows or the
   allocation result.
8. **Size the compiled tier's memory floor.** §1.1's ≈400 KB is tier 1's and
   stays there. This tier needs its own number, and `blit565`'s 153,600-byte
   framebuffer is most of the reason. Wants one integrated cart (item 3) to
   measure against rather than a derivation.
