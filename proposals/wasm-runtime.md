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

## The framebuffer contract — the one new verb

The measured blocker is not speed but the boundary: a compiled cart reaching
pixels through the `pix` import pays a trampoline per pixel — 76,800 crossings
per frame, dead at any VM speed. The fix is one import:

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
fixed hardware and fits §2.2 as-is. The GB's 4 shades likewise. GBA/SNES
titles at full palette load stay out — > 64 simultaneous is the line, and
per-scanline palettes are a bridge deliberately not crossed.)

Measured budget: ~4.6 M pixel-writes/s from AOT code into linear memory against
476 M ops/s of arithmetic — a full-screen software raster lands ~17 ms on the
measured board, inside a 30 fps frame with the geometry effectively free. This
does not reopen §12.6: the cart writes *its own* memory, the host's framebuffer
stays opaque, and hosts keep every freedom of depth, scale and byte order.

Assets stay host-side (`spr`, `map`, `sspr` render as ever). A later revision may
add read-only asset access into linear memory (`sheet_read(ptr)`-shaped) if a
ported engine demonstrates the need; it is deliberately absent until one does.

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
   frame loop, not a bare harness.
3. **One integrated cart** — the flat-shaded raycaster in C is the natural twin,
   since its Lua sibling is already measured on glass.
4. **A wasm twin of one conformance scene** passing the existing goldens — the
   moment this binding becomes testable rather than argued.
5. **`moy_cart.h`** committed here once the import list survives item 3.
6. **User-file access** (moybyte#108) is orthogonal but blocks the e-reader class
   of ports either way; the WASI-subset question belongs to that issue, not this
   one.
