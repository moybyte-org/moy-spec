/* The browser player's compiled carts (cart.c, and page/cart.js).
 *
 * A "runtime": "wasm" cart runs as a SIBLING of this module: the page
 * instantiates the cart's own main.wasm with the browser's engine, and its
 * "moy" imports are JavaScript adapters over the import table libmoy's wasm
 * binding exports (src/moy_wasm.c under MOY_WASM_JS). Never an engine inside
 * this module.
 *
 * The binding needs the direct-colour raster and Lua carts keep the index
 * one, so cart.c and the second copy of the raster are built with
 * -DMOY_PIXEL_RGB565 -include port/moy565.h. main.c and cart.c each include
 * this under their own build, so nothing here names a libmoy type that
 * differs between the two.
 */

#ifndef MOY_WEB_CART_H
#define MOY_WEB_CART_H

#include <stddef.h>
#include <stdint.h>

/* The cart's sample stream: its rate and the most the player holds, which are
 * moy_wasm.h's MOY_WASM_SND_RATE and MOY_WASM_SND_DEPTH (cart.c checks that
 * they agree). */
#define WEB_CART_SND_RATE  22050
#define WEB_CART_SND_DEPTH 2048

typedef struct {
    const uint8_t *module;      /* main.wasm, all of it */
    size_t size;
    uint32_t pages;             /* the manifest's "memory" */
    int w, h;                   /* the manifest's canvas */
    const uint8_t *palette;     /* the cart's 64 RGB entries, or NULL */
    uint8_t *sheet;             /* MOY_SHEET_W * MOY_SHEET_H, main.c's */
    uint8_t *cells;             /* map_w * map_h, main.c's */
    int map_w, map_h;
    uint8_t *flags;             /* MOY_FLAGS, main.c's */
    /* main.c's moy_host. The two builds' moy_host differ only in the pixel
     * type the layer pair names, which cart.c supplies itself, so the rest is
     * copied as it stands. background is not taken: the binding repaints the
     * screen before each _draw. */
    const void *host;
    /* The cart's own files, for `read`: moy_wasm's read callback. */
    uint32_t (*read)(void *user, const char *name, uint32_t offset,
                     uint8_t *dst, uint32_t len);
    /* The cart's `snd`: moy_wasm's snd callback. */
    uint32_t (*snd)(void *user, const uint8_t *pcm, uint32_t n);
    uint32_t seed;              /* rnd()'s */
    uint64_t limit;             /* the most a cart may take to load, in bytes */
} web_cart_config;

/* Check the cart before anything of it exists -- its footprint against the
 * limit, its module against SPEC.md 16's shape -- and bind a fresh console
 * to it. Returns the binding (the moy_wasm the page's adapters call the table
 * with), or NULL with the refusal in `err`: a plain sentence for the player. */
void *web_cart_open(const web_cart_config *cfg, char *err, size_t errlen);

/* The per-frame draw-state reset main.c gives its own canvas. */
void web_cart_reset_state(void);

/* The screen as it stands: w * h canonical RGB565 words, or NULL. */
const uint16_t *web_cart_frame(void);

/* Release the cart's layers and its screen; safe when none is open. */
void web_cart_close(void);

#endif /* MOY_WEB_CART_H */
