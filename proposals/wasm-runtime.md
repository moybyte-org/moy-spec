# Proposal: `runtime: "wasm"` — the compiled-cart binding

**Status: promoted (2026-09-30).** The binding is SPEC.md §16, an optional second
binding beside Lua (§15). What this proposal held now lives where each part is read:

| what | where |
|---|---|
| the contract: the cart, the module shape, the import table, marshalling, `blit` and `blit565`, `read`, memory, traps, `snd`, `par`, determinism | SPEC.md §16 |
| the import table as data | `wasm-imports.json` |
| the import table as C, for a cart | `libmoy/include/moy_cart.h` |
| the measurements and the reasoning behind each value | RATIONALE.md, "The WebAssembly binding" |
| how a host executes a module, distribution, the integration frictions | PORTING.md, "Compiled carts" |

The evidence runs are moybyte#158's. What stays here is the list of open items,
numbered as the issues cite them.

## Open items

Decided items stay in the list, struck, with the date they closed, so the
numbering the issues cite keeps meaning.

1. ~~**Xtensa AOT on the floor board.**~~ **Measured 2026-09-24:** in scope, and it
   skips the install entirely — on both boards the module loads from a file into
   PSRAM. The floor board runs the same core at well under half the RISC-V
   board's rate, and Doom runs on its glass; numbers in moybyte#158.
2. ~~**Measure `blit` through a console's frame loop**, not a bare harness.~~
   **Measured 2026-09-25:** a full-frame blit cart inside the reference console's
   frame loop on all four of its boards, then Doom through `blit` and Jet Teapot
   through `blit565`; each board's cost per format is in moybyte#158.
3. ~~**One integrated cart.**~~ **Landed 2026-09-26, twice over:** Doom
   (doomgeneric, through `blit`, `read` and `snd`) and the Jet carts (Jet Teapot and
   ESP 88, through `blit565`, `read` and `par`) run from the reference console's
   launcher, under guards in its on-glass suites. The raycaster twin the item
   first named was never needed.
4. ~~**A wasm twin of one conformance scene** passing an RGB565 golden
   (Determinism).~~ **Landed 2026-09-26:** `conformance/wasm_run.py` holds a
   scene per import only this binding has, the ordinary verbs through it, §11's
   `primitives` as a compiled cart, and a trap to RGB565 goldens, and refuses
   the shape fixtures, on three hosts of libmoy's binding: its WAMR harness, the
   desktop player and the web player, where the cart is a sibling module.
5. ~~**`moy_cart.h`** committed here once the import list survives item 3.~~
   **Landed 2026-09-30:** `libmoy/include/moy_cart.h`, which
   `libmoy/test/wasm_table_check.py` holds to `wasm-imports.json` row for row.
6. **User-file access** (moybyte#108) is orthogonal to the cart-local `read`
   (item 10) and would be a separate import; it blocks the e-reader class of ports
   either way, and the WASI-subset question belongs to that issue, not this one.
7. ~~**The `blit565` penalty on the floor board.**~~ **Measured 2026-08-06**, and
   the prediction held with room to spare: the cart-side cost widened from
   +4.5–31 % to 1.1–3.3×, and the host-side saving went negative (RATIONALE.md).
   What remains open is only the bus speed: the floor-board run is at 80 MHz PSRAM
   because that board's flash is not verified for the high-performance mode
   `SPIRAM_SPEED_120M` needs. A 120 MHz rerun on verified flash would shrink the
   PSRAM-resident margins; it cannot reach the internal-SRAM rows or the
   allocation result.
8. **The figure for the compiled tier's memory floor.** Which number the binding
   uses is decided (SPEC.md §16.7): the floor board's share of the cart-runtime
   reserve, measured with the runtime resident, against the integrated carts
   (item 3) rather than a derivation. What the floor bounds is the cart's whole
   footprint while it loads, not `"memory"` alone: the declared linear memory, the
   compiled module's code and the engine's working pool are all resident at once,
   and on the reference console the code and pool of the first real port were over
   a megabyte of its load peak (moybyte#158). A check that bounds `"memory"`
   against the floor therefore has to leave that margin, and the figure lands in
   §16.7 and in `moy check`'s constant together, with the margin stated beside it.
   What the check does with the figure is decided: a cart above the floor draws a
   warning that names it, and the console that cannot fit the cart is the one that
   refuses it.
9. ~~**The `blit` palette is too small for the first real port.**~~ **Decided
   2026-09-25:** 256 entries, 768 bytes of RGB (RATIONALE.md).
10. ~~**A ported engine needs to read its own assets.**~~ **Decided 2026-09-25:**
    `read`, read-only and scoped to the cart's own folder, pinned without waiting
    on the user-file question (item 6). The clock Doom also wanted is §9's
    `time()`, and there is no clock import.
11. ~~**PCM audio's shape**~~ **Decided 2026-09-29:** 22,050 Hz, mono, signed
    16-bit, and a queue of 2,048 frames, pinned by Doom, the first cart to need
    them (RATIONALE.md). `snd` is in the import table, and a host with no audio
    drains its queue at the rate.
12. ~~**More than one core.**~~ **Decided 2026-09-29:** `par`, fork-join over the
    cart's own unshared memory, and not the threads proposal (RATIONALE.md);
    moybyte#158 has what it measures against one core and against native two-core
    rendering.
