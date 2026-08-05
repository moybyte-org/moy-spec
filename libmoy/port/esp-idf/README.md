# libmoy on ESP-IDF

**Status: the component builds as an IDF component; the shim below is written
from the SDL2 port and the reference console's device layer, and has NOT been
run on hardware from this repository.** That is the honest state — say so
rather than discover it later. The parts that *have* been verified on an
ESP32-P4 are the raster and the C kernel it mirrors, through moy-spec's
conformance suite (see `conformance/`, and moybyte's `tools/p4_conformance.py`).

## Using it

Add to your project's `CMakeLists.txt`:

```cmake
set(EXTRA_COMPONENT_DIRS "path/to/libmoy/port/esp-idf")
```

then `#include "moy.h"`. `CONFIG_MOY_WITH_LUA` (on by default) brings the Lua
binding and the vendored VM; turn it off if your host drives the console from C.

## What you actually implement

The same four things the SDL2 port implements, and nothing else:

| | on ESP32 |
|---|---|
| **pixels out** | `moy_palette_rgb565(&canvas, NULL, fb)` then your panel's flush — `esp_lcd_panel_draw_bitmap`, a DMA descriptor, whatever you have |
| **buttons in** | GPIO or a touch region → the seven `moy_button` values |
| **a clock** | `esp_timer_get_time() / 1000` |
| **persistence** | 256 signed 32-bit slots → NVS, a blob, or a file on SD |

```c
static uint8_t framebuffer[MOY_W * MOY_H];      /* 75 KB, SPEC.md 1.1 */
static uint8_t sheet_pix[MOY_SHEET_W * MOY_SHEET_H];   /* 32 KB */
static uint8_t map_cells[128 * 128];            /* 16 KB */

moy_canvas  canvas;
moy_sheet   sheet;
moy_map     map;
moy_console con;

moy_canvas_init(&canvas, framebuffer, MOY_W, MOY_H);
moy_sheet_init(&sheet, sheet_pix);
moy_map_init(&map, map_cells, 20, 15);
moy_console_init(&con, &canvas, &sheet, &map);

con.host.btn      = my_btn;
con.host.btnp     = my_btnp;
con.host.players  = my_players;
con.host.time_ms  = my_millis;
con.host.pmem_get = my_pmem_get;
con.host.pmem_set = my_pmem_set;
con.host.quit     = my_quit;
```

Then per frame: `moy_reset_state(&canvas)`, run the cart's `_update`/`_draw`,
resolve the framebuffer, flush.

## Memory

SPEC.md 1.1's floor is about 400 KB and the buffers above are most of it. On
PSRAM-equipped parts that is nothing; the spec deliberately excludes SRAM-only
microcontrollers (§12.4). **Where** the buffers live is yours: the reference
console keeps its framebuffer and assets in PSRAM and steers only the Lua VM's
hot allocations to internal SRAM, having measured an all-PSRAM heap at roughly
2× slower cart logic on one board's 120 MHz octal bus. A cart can observe none
of this.

libmoy never allocates, so every one of those buffers is placed by you —
`EXT_RAM_BSS_ATTR`, a `heap_caps_malloc` with `MALLOC_CAP_SPIRAM`, or plain
static.

## Performance

The raster is straightforward C. `moy_rect` and `moy_cls` are `memset` per
span, which is where most fill time goes and is already the fast path; per-pixel
verbs go through a single clipped write.

If you have a hardware blitter or a tuned assembly kernel, the honest way to use
it is to keep libmoy as the definition and check yours against it: build
`test/trace_replay` for your target, run the conformance suite, and require
pixel-identical output. That is exactly how the reference console's C kernel is
checked, and it turned up two real bugs the first time it ran.
