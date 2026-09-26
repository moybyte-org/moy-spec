/* The desktop player's compiled carts (wasm_cart.c).
 *
 * A "runtime": "wasm" cart runs on libmoy's wasm binding over WAMR's
 * interpreter, on the direct-colour raster the binding needs, linked under
 * its moy565_ names (port/moy565.h) beside the index raster main.c runs Lua
 * carts on. main.c and wasm_cart.c each include this under their own build,
 * so nothing here names a libmoy type that differs between the two.
 */

#ifndef MOY_PLAY_WASM_CART_H
#define MOY_PLAY_WASM_CART_H

#include <stddef.h>
#include <stdint.h>

typedef struct wasm_cart wasm_cart;

typedef struct {
    const char *dir;            /* the cart folder: `read`'s only root */
    const char *main;           /* the module, a name in it */
    uint32_t pages;             /* the manifest's "memory" */
    int w, h;                   /* the manifest's canvas */
    const uint8_t *palette;     /* the cart's 64 RGB entries, or NULL */
    uint8_t *sheet;             /* MOY_SHEET_W * MOY_SHEET_H, main.c's */
    uint8_t *cells;             /* map_w * map_h, main.c's */
    int map_w, map_h;
    uint8_t *flags;             /* MOY_FLAGS, main.c's */
    /* main.c's moy_host. The two builds' moy_host differ only in the pixel
     * type the layer pair names, which wasm_cart.c supplies itself, so the
     * rest is copied as it stands. background is not taken: the binding
     * repaints the screen before each _draw. */
    const void *host;
    uint32_t seed;              /* rnd()'s */
    uint64_t limit;             /* the most a cart may take to load, in bytes */
} wasm_cart_config;

/* Check the cart and load it: its footprint against cfg->limit, then its
 * module against the proposal's shape, before its memory exists. NULL with
 * the refusal in `err` -- a plain sentence for the player. */
wasm_cart *wasm_cart_open(const wasm_cart_config *cfg, char *err, size_t errlen);

/* The three hooks. Non-zero on a trap, with the message in `err`; a trapped
 * cart is never called again, and the frame a trapped draw left is partial
 * and never presented. quit() calls the host's quit hook and returns 0. */
int wasm_cart_init(wasm_cart *c, char *err, size_t errlen);
int wasm_cart_update(wasm_cart *c, float dt, char *err, size_t errlen);
int wasm_cart_draw(wasm_cart *c, char *err, size_t errlen);

/* The per-frame draw-state reset main.c gives its own canvas. */
void wasm_cart_reset_state(wasm_cart *c);

/* The screen as it stands: w * h canonical RGB565 words. */
const uint16_t *wasm_cart_frame(const wasm_cart *c);

void wasm_cart_close(wasm_cart *c);

#endif /* MOY_PLAY_WASM_CART_H */
