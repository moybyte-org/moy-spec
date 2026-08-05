/* libmoy -- the moy console, as a C library.
 *
 * https://github.com/moybyte-org/moy-spec is the spec; this implements its
 * raster and cart model in plain C99 with no dependencies, no allocation, and
 * no opinions about your platform.
 *
 * WHY IT EXISTS. moy's premise is that several vendors' handhelds run the same
 * cart. The reference implementation is MicroPython, so "implement moy" has so
 * far meant "adopt MicroPython" -- a large ask of an ESP-IDF or Arduino
 * firmware author, and the wrong one, because none of it is what the spec
 * actually requires. Here the whole console is a library you link, and the only
 * thing you write is the part that is genuinely yours: pixels out, buttons in.
 *
 * THE CONTRACT.
 *   - No allocation. You own every buffer; the library never calls malloc.
 *     A moy_canvas is a struct you can place in static storage or PSRAM.
 *   - No I/O, no time, no threads. Nothing here reads a file or a clock.
 *   - C99, freestanding-friendly: string.h and math.h are the only headers,
 *     and math.h only for sqrt in circ().
 *   - Every drawing verb honours camera, clip, pal and palt (SPEC.md 6),
 *     because they all funnel through moy_put or moy_rect.
 *
 * WHAT IT DELIBERATELY DOES NOT DO. There is no Lua VM in here, and no host
 * loop. The cart language is a binding on top of this (SPEC.md 4 says Lua 5.4,
 * and which Lua that is belongs to you), and the frame loop belongs to your
 * platform. That seam is the point: the verb table is the narrow waist, so a
 * Lua binding, a WASM import table and a native binding are each a few hundred
 * lines of glue rather than a new port of the console.
 *
 * VERIFICATION. libmoy is checked against the spec's own conformance suite --
 * the same golden frames the WebAssembly player and an ESP32-P4 are checked
 * against. See test/.
 *
 * MIT licensed, on purpose: a spec is only portable if its core is.
 */

#ifndef MOY_H_INCLUDED
#define MOY_H_INCLUDED

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#define MOY_VERSION "0.1.0"

/* SPEC.md 1: the console is a fixed-size machine. */
#define MOY_W            320
#define MOY_H            240
#define MOY_PALETTE      64      /* SPEC.md 2 */
#define MOY_TILE         8
#define MOY_SHEET_COLS   16      /* SPEC.md 3.2: 128 x 256 pixels ... */
#define MOY_SHEET_ROWS   32
#define MOY_SHEET_W      (MOY_SHEET_COLS * MOY_TILE)
#define MOY_SHEET_H      (MOY_SHEET_ROWS * MOY_TILE)
#define MOY_TILES        (MOY_SHEET_COLS * MOY_SHEET_ROWS)   /* ... 512 tiles */
#define MOY_MAP_MAX      128     /* SPEC.md 3.3: 128 x 128 cells = 16 KB */
#define MOY_MAP_MAX_ID   254     /* a cell holds id+1 in one byte */

/* SPEC.md 7.1 flip bits. */
#define MOY_FLIP_NONE 0
#define MOY_FLIP_X    1
#define MOY_FLIP_Y    2
#define MOY_FLIP_XY   3

/* The framebuffer is palette INDICES, one byte per pixel (SPEC.md 1). Your
 * display almost certainly wants something else; resolve at flush time with
 * moy_palette_rgb565 / moy_palette_rgb888, which is the only place the console
 * cares what a colour looks like. */
typedef struct {
    uint8_t *pix;                /* w*h indices -- YOURS, never allocated here */
    int      w, h;
    int      cam_x, cam_y;       /* SPEC.md 6 camera */
    int      clip_x0, clip_y0;   /* SPEC.md 6 clip, screen space (post-camera) */
    int      clip_x1, clip_y1;
    uint8_t  pal[MOY_PALETTE];   /* draw-time index remap */
    uint8_t  palt[MOY_PALETTE];  /* per-index sprite transparency */
} moy_canvas;

/* SPEC.md 3.2: sprite pixels are indices 0-15, one nibble each on disk. */
typedef struct {
    uint8_t *pix;                /* MOY_SHEET_W * MOY_SHEET_H, yours */
} moy_sheet;

/* SPEC.md 3.3: one byte per cell holding tile_id + 1, so 0 is empty. */
typedef struct {
    uint8_t *cells;              /* w*h, yours */
    int      w, h;
} moy_map;

/* -- lifecycle ---------------------------------------------------------- */

/* Point a canvas at your buffer and reset its draw state. `pix` must hold
 * w*h bytes. Sizes other than 320x240 exist for the `layers` extension. */
void moy_canvas_init(moy_canvas *c, uint8_t *pix, int w, int h);

/* Camera to 0,0; clip to full screen; pal to identity; palt all opaque.
 * A host calls this before each cart frame: draw state is per-frame and must
 * not leak between carts, or from host UI into a cart's first frame. */
void moy_reset_state(moy_canvas *c);

/* -- drawing (SPEC.md 6) ------------------------------------------------- */

void moy_cls   (moy_canvas *c, int col);
void moy_pix   (moy_canvas *c, int x, int y, int col);
int  moy_pget  (const moy_canvas *c, int x, int y);   /* camera-relative; 0 outside */
void moy_line  (moy_canvas *c, int x0, int y0, int x1, int y1, int col);
void moy_rect  (moy_canvas *c, int x, int y, int w, int h, int col);  /* FILLED */
void moy_rectb (moy_canvas *c, int x, int y, int w, int h, int col);  /* outline */
void moy_circ  (moy_canvas *c, int cx, int cy, int r, int col);       /* FILLED */
void moy_circb (moy_canvas *c, int cx, int cy, int r, int col);       /* outline */

/* Text, fixed 8px cell. `s` is BYTES and `len` their count -- SPEC.md 6 says
 * print walks bytes, not characters, because a Lua string is a byte string and
 * a host that decoded first would advance the cursor differently from one that
 * did not. Bytes outside 0x20-0x7F draw nothing and still advance. */
void moy_print (moy_canvas *c, const uint8_t *s, size_t len, int x, int y, int col);

void moy_camera(moy_canvas *c, int x, int y);
void moy_camera_reset(moy_canvas *c);
void moy_clip  (moy_canvas *c, int x, int y, int w, int h);
void moy_clip_reset(moy_canvas *c);
void moy_pal   (moy_canvas *c, int c0, int c1);
void moy_pal_reset(moy_canvas *c);
void moy_palt  (moy_canvas *c, int col, int on);
void moy_palt_reset(moy_canvas *c);

/* PROVISIONAL -- SPEC.md 6.1 is unsettled and these are not part of core 0.1. */
void moy_tri   (moy_canvas *c, int x1, int y1, int x2, int y2, int x3, int y3, int col);
void moy_trib  (moy_canvas *c, int x1, int y1, int x2, int y2, int x3, int y3, int col);

/* -- sprites and map (SPEC.md 7.1, 7.2) ---------------------------------- */

void moy_sheet_init(moy_sheet *s, uint8_t *pix);
int  moy_sheet_pget(const moy_sheet *s, int x, int y);

/* Tile `n` of 0..511 at x,y. `colorkey` is the transparent index or -1 for
 * opaque; `scale` an integer enlargement; `flip` one of MOY_FLIP_*. A tile id
 * out of range draws nothing -- SPEC.md 3.2 lets a short sheet leave the rest
 * blank, so asking for a blank tile is legal. */
void moy_spr(moy_canvas *c, const moy_sheet *s, int n, int x, int y,
             int colorkey, int scale, int flip);

/* Stretch a sheet PIXEL region into a dw x dh rect, nearest-neighbour.
 * PROVISIONAL (SPEC.md 6.1). */
void moy_sspr(moy_canvas *c, const moy_sheet *s, int sx, int sy, int sw, int sh,
              int dx, int dy, int dw, int dh, int colorkey, int flip);

void moy_map_init(moy_map *m, uint8_t *cells, int w, int h);
int  moy_mget(const moy_map *m, int x, int y);          /* -1 empty OR out of range */
void moy_mset(moy_map *m, int x, int y, int tile);      /* negative clears */
void moy_map_draw(moy_canvas *c, const moy_map *m, const moy_sheet *s,
                  int mx, int my, int w, int h, int sx, int sy,
                  int colorkey, int scale);

/* -- palette and font (SPEC.md 2, 6) ------------------------------------- */

/* The default table, straight from the spec's palette.json (generated, see
 * tools/embed_data.py). 64 entries of r,g,b. A cart may replace it wholesale
 * (SPEC.md 2.2) -- pass your own to the resolvers below. */
extern const uint8_t moy_palette_default[MOY_PALETTE * 3];

/* The 8x8 font, from the spec's font.bin: 96 glyphs for 0x20-0x7F, 8 bytes per
 * glyph, one byte per COLUMN, LSB = top row. */
extern const uint8_t moy_font_data[96 * 8];

/* Resolve the whole framebuffer at flush time. `pal` may be NULL for the
 * default. rgb565 is big-endian, which is what most panels want. */
void moy_palette_rgb888(const moy_canvas *c, const uint8_t *pal, uint8_t *out);
void moy_palette_rgb565(const moy_canvas *c, const uint8_t *pal, uint16_t *out);

#ifdef __cplusplus
}
#endif
#endif /* MOY_H_INCLUDED */
