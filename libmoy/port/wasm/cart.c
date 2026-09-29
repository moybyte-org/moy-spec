/* The browser player's compiled carts: the console half.
 *
 * Built with -DMOY_PIXEL_RGB565 -DMOY_WASM_JS -include port/moy565.h, so the
 * moy_* calls below reach the direct-colour raster under its moy565_ names
 * and main.c keeps the index one. The import table, the marshalling, the
 * blit, the read and the traps are src/moy_wasm.c's -- the file every other
 * host of the binding runs. The cart itself is not here: page/cart.js
 * instantiates it as a sibling module with the browser's own engine and
 * adapts each of its "moy" imports onto the table.
 *
 * What C cannot do is address the cart's memory, which is a different
 * WebAssembly.Memory from this module's, or call into the cart. The three
 * functions the binding asks of its embedder for those are here, in
 * JavaScript: two hand the binding copies -- a range of the cart's memory
 * copied in, or bytes copied back out -- and one runs one of par's items.
 */

#include <stdlib.h>
#include <string.h>
#include <stdio.h>

#include <emscripten.h>

#include "moy.h"
#include "moy_wasm.h"
#include "cart.h"

#define KEEP EMSCRIPTEN_KEEPALIVE

#if WEB_CART_SND_RATE != MOY_WASM_SND_RATE || WEB_CART_SND_DEPTH != MOY_WASM_SND_DEPTH
#error "cart.h's stream is not moy_wasm.h's"
#endif

/* page/cart.js sets Module.moyCart while a cart is bound. */
EM_JS(uint8_t *, moy_wasm_js_span, (moy_wasm *w, uint32_t offset, uint32_t n), {
    return Module.moyCart ? Module.moyCart.span(offset >>> 0, n >>> 0) : 0;
});

EM_JS(int, moy_wasm_js_store, (moy_wasm *w, uint32_t offset, const uint8_t *src, uint32_t n), {
    return Module.moyCart ? Module.moyCart.store(offset >>> 0, src, n >>> 0) : 0;
});

/* A par item, which the page runs on the cart itself: a page has one core to
 * give a cart, so the binding runs the items here, one after another. */
EM_JS(int, moy_wasm_js_item, (moy_wasm *w, int32_t i, int32_t arg, uint32_t sp), {
    return Module.moyCart ? Module.moyCart.item(i, arg, sp >>> 0) : 1;
});

static moy_canvas canvas;
static moy_sheet sheet;
static moy_map map;
static moy_console con;
static moy_wasm binding;
static moy_pixel *screen;

static moy_pixel *layer_new(void *u, int w, int h)
{
    (void)u;
    return (moy_pixel *)calloc((size_t)w * (size_t)h, sizeof(moy_pixel));
}

static void layer_free(void *u, moy_pixel *p) { (void)u; free(p); }

void *web_cart_open(const web_cart_config *cfg, char *err, size_t errlen)
{
    uint64_t need;
    int i;

    web_cart_close();
    if (!cfg->pages) {
        snprintf(err, errlen, "this cart declares no \"memory\", which a compiled cart must");
        return NULL;
    }
    /* What loading it takes, before any of it is taken: the declared memory
     * and the module. How the browser compiles the module is its own. */
    need = (uint64_t)cfg->pages * 65536u + (uint64_t)cfg->size;
    if (need > cfg->limit) {
        snprintf(err, errlen, "this cart needs %llu KiB to load and this player gives a "
                 "cart %llu KiB, so it does not start",
                 (unsigned long long)(need / 1024u),
                 (unsigned long long)(cfg->limit / 1024u));
        return NULL;
    }
    {
        char why[256];
        if (moy_wasm_check_bytes(cfg->module, cfg->size, cfg->pages, why, sizeof why)) {
            snprintf(err, errlen, "this cart's module is refused: %s", why);
            return NULL;
        }
    }

    screen = (moy_pixel *)calloc((size_t)cfg->w * (size_t)cfg->h, sizeof(moy_pixel));
    if (!screen) {
        snprintf(err, errlen, "out of memory");
        return NULL;
    }
    moy_canvas_init(&canvas, screen, cfg->w, cfg->h);
    if (cfg->palette) {
        uint16_t wire[MOY_PALETTE];
        for (i = 0; i < MOY_PALETTE; i++) {
            const uint8_t *e = cfg->palette + i * 3;
            wire[i] = (uint16_t)(((e[0] & 0xF8u) << 8) | ((e[1] & 0xFCu) << 3) | (e[2] >> 3));
        }
        moy_canvas_wire(&canvas, wire);
    }
    moy_sheet_init(&sheet, cfg->sheet);
    moy_map_init(&map, cfg->cells, cfg->map_w, cfg->map_h);
    moy_console_init(&con, &canvas, &sheet, &map);
    memcpy(&con.host, cfg->host, sizeof con.host);
    con.host.layer_new = layer_new;
    con.host.layer_free = layer_free;
    con.host.background = NULL;
    con.flags = cfg->flags;
    moy_srand(&con, cfg->seed);

    memset(&binding, 0, sizeof binding);
    binding.read = cfg->read;
    binding.snd = cfg->snd;
    moy_wasm_bind(&binding, &con);
    return &binding;
}

void web_cart_reset_state(void)
{
    if (screen) moy_reset_state(&canvas);
}

const uint16_t *web_cart_frame(void) { return screen; }

void web_cart_close(void)
{
    moy_wasm_close(&binding);
    memset(&binding, 0, sizeof binding);
    free(screen);
    screen = NULL;
}

/* The table and the hooks' brackets, for page/cart.js. */
KEEP const NativeSymbol *moy_web_natives(uint32_t *count) { return moy_wasm_natives(count); }
KEEP void moy_web_begin(moy_wasm *w, int hook) { moy_wasm_begin(w, hook); }
KEEP int moy_web_end(moy_wasm *w, int threw) { return moy_wasm_end(w, threw); }
KEEP const char *moy_web_trapped(const moy_wasm *w) { return moy_wasm_trapped(w); }
KEEP void moy_web_item_trap(moy_wasm *w, const char *msg) { moy_wasm_item_trap(w, msg); }
