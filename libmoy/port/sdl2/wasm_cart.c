/* The desktop player's compiled carts: libmoy's wasm binding, over WAMR.
 *
 * Built with -DMOY_PIXEL_RGB565 -DMOY_WASM -include port/moy565.h, so the
 * moy_* calls below reach the direct-colour raster under its moy565_ names
 * and main.c keeps the index one. The import table, the marshalling, the
 * blit, the read and the traps are src/moy_wasm.c's -- the same file every
 * other host of this binding runs. What is here is the part SPEC.md 16
 * leaves to a host: how the module is loaded and run, and how much a cart
 * may take.
 *
 * The desktop runs the cart's own main.wasm on WAMR's interpreter: no
 * compiler, no per-architecture module, and fast enough for a desktop,
 * which is host policy and nothing a cart can observe. A cart's par items
 * run on lanes over POSIX threads (port/moy_lanes.c), one for each core the
 * machine has beside the one the cart runs on, up to the binding's limit.
 * Its written files are kept in the folder main.c names (port/moy_files.c).
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "moy.h"
#include "moy_wasm.h"
#include "../moy_lanes.h"
#include "../moy_files.h"
#include "wasm_cart.h"

#if WASM_CART_SND_RATE != MOY_WASM_SND_RATE || WASM_CART_SND_DEPTH != MOY_WASM_SND_DEPTH
#error "wasm_cart.h's stream is not moy_wasm.h's"
#endif

/* The interpreter's operand and call stack, per cart. */
#define CART_STACK (256 * 1024)
#define CART_PATH 1024

struct wasm_cart {
    char dir[CART_PATH];
    uint8_t *bytes;             /* the module file, held while it is loaded */
    wasm_module_t module;
    wasm_module_inst_t inst;
    wasm_exec_env_t env;
    moy_canvas canvas;
    moy_sheet sheet;
    moy_map map;
    moy_console con;
    moy_wasm w;
    moy_lanes *lanes;
    moy_files *files;
    char *writable;
    moy_pixel *screen;
};

static int runtime_up;
/* WAMR sorts the registered table in place and points at it until the runtime
 * is destroyed, which in this player is never. */
static NativeSymbol *natives;

static int runtime(void)
{
    uint32_t n = 0;
    if (runtime_up) return 1;
    moy_wasm_natives(&n);
    natives = (NativeSymbol *)calloc(n, sizeof *natives);
    if (!natives || !wasm_runtime_init()) return 0;
    wasm_runtime_set_log_level(WASM_LOG_LEVEL_FATAL);
    if (moy_wasm_register(natives) != 0) return 0;
    runtime_up = 1;
    return 1;
}

/* The cart's own files, and nothing else. The binding has already held the
 * name inside the folder, so joining it to the folder cannot leave it. */
static uint32_t cart_read(void *user, const char *name, uint32_t offset,
                          uint8_t *dst, uint32_t len)
{
    wasm_cart *c = (wasm_cart *)user;
    char path[CART_PATH + 260];
    FILE *f;
    long size;
    uint32_t got = 0;
    snprintf(path, sizeof path, "%s/%s", c->dir, name);
    f = fopen(path, "rb");
    if (!f) return 0;
    /* A name that opens and will not read -- a folder, where the system opens
     * one -- is not a file of the cart's, and reads as absent. */
    if (fgetc(f) == EOF && ferror(f)) {
        fclose(f);
        return 0;
    }
    if (fseek(f, 0, SEEK_END) == 0 && (size = ftell(f)) >= 0
        && (unsigned long)size > offset) {
        uint32_t left = (uint32_t)((unsigned long)size - offset);
        if (len == 0) got = left;
        else if (fseek(f, (long)offset, SEEK_SET) == 0)
            got = (uint32_t)fread(dst, 1, len < left ? len : left, f);
    }
    fclose(f);
    return got;
}

/* A desktop has no reason to stop at SPEC.md 1.1's one layer; the binding's
 * own table caps how many a cart holds. */
static moy_pixel *layer_new(void *u, int w, int h)
{
    (void)u;
    return (moy_pixel *)calloc((size_t)w * (size_t)h, sizeof(moy_pixel));
}

static void layer_free(void *u, moy_pixel *p) { (void)u; free(p); }

static uint8_t *slurp(const char *path, long *n)
{
    FILE *f = fopen(path, "rb");
    uint8_t *b = NULL;
    long size;
    if (!f) return NULL;
    if (fseek(f, 0, SEEK_END) == 0 && (size = ftell(f)) > 0
        && fseek(f, 0, SEEK_SET) == 0 && (b = (uint8_t *)malloc((size_t)size)) != NULL
        && fread(b, 1, (size_t)size, f) != (size_t)size) {
        free(b);
        b = NULL;
    }
    if (b) *n = size;
    fclose(f);
    return b;
}

wasm_cart *wasm_cart_open(const wasm_cart_config *cfg, char *err, size_t errlen)
{
    char path[CART_PATH + 260], msg[256];
    wasm_cart *c;
    uint8_t *copy;
    uint64_t need;
    long n = 0;
    int i;

    if (!cfg->pages) {
        snprintf(err, errlen, "this cart declares no \"memory\", which a compiled cart must");
        return NULL;
    }
    snprintf(path, sizeof path, "%s/%s", cfg->dir, cfg->main);
    c = (wasm_cart *)calloc(1, sizeof *c);
    if (!c) {
        snprintf(err, errlen, "out of memory");
        return NULL;
    }
    c->bytes = slurp(path, &n);
    if (!c->bytes) {
        snprintf(err, errlen, "cannot read %s", path);
        free(c);
        return NULL;
    }

    /* What loading it takes, before any of it is taken: the declared memory,
     * the module and the interpreter's stack. */
    need = (uint64_t)cfg->pages * 65536u + (uint64_t)n + CART_STACK;
    if (need > cfg->limit) {
        snprintf(err, errlen, "this cart needs %llu KiB to load and this player gives a "
                 "cart %llu KiB, so it does not start (--memory-limit raises it)",
                 (unsigned long long)(need / 1024u),
                 (unsigned long long)(cfg->limit / 1024u));
        wasm_cart_close(c);
        return NULL;
    }
    if (!runtime()) {
        snprintf(err, errlen, "the wasm runtime did not start");
        wasm_cart_close(c);
        return NULL;
    }

    /* WAMR may rewrite the buffer it loads from, so the check reads a copy. */
    copy = (uint8_t *)malloc((size_t)n);
    if (!copy) {
        snprintf(err, errlen, "out of memory");
        wasm_cart_close(c);
        return NULL;
    }
    memcpy(copy, c->bytes, (size_t)n);
    msg[0] = 0;
    c->module = wasm_runtime_load(c->bytes, (uint32_t)n, msg, sizeof msg);
    if (!c->module || moy_wasm_check(c->module, copy, (size_t)n, cfg->pages, msg, sizeof msg)) {
        snprintf(err, errlen, "this cart's module is refused: %s", msg);
        free(copy);
        wasm_cart_close(c);
        return NULL;
    }
    free(copy);
    c->inst = wasm_runtime_instantiate(c->module, CART_STACK, 0, msg, sizeof msg);
    if (c->inst) c->env = wasm_runtime_create_exec_env(c->inst, CART_STACK);
    if (!c->env) {
        snprintf(err, errlen, "this cart does not start: %s", c->inst ? "no exec env" : msg);
        wasm_cart_close(c);
        return NULL;
    }

    c->screen = (moy_pixel *)calloc((size_t)cfg->w * (size_t)cfg->h, sizeof(moy_pixel));
    if (!c->screen) {
        snprintf(err, errlen, "out of memory");
        wasm_cart_close(c);
        return NULL;
    }
    moy_canvas_init(&c->canvas, c->screen, cfg->w, cfg->h);
    if (cfg->palette) {
        uint16_t wire[MOY_PALETTE];
        for (i = 0; i < MOY_PALETTE; i++) {
            const uint8_t *e = cfg->palette + i * 3;
            wire[i] = (uint16_t)(((e[0] & 0xF8u) << 8) | ((e[1] & 0xFCu) << 3) | (e[2] >> 3));
        }
        moy_canvas_wire(&c->canvas, wire);
    }
    moy_sheet_init(&c->sheet, cfg->sheet);
    moy_map_init(&c->map, cfg->cells, cfg->map_w, cfg->map_h);
    moy_console_init(&c->con, &c->canvas, &c->sheet, &c->map);
    memcpy(&c->con.host, cfg->host, sizeof c->con.host);
    c->con.host.layer_new = layer_new;
    c->con.host.layer_free = layer_free;
    c->con.host.background = NULL;
    c->con.flags = cfg->flags;
    moy_srand(&c->con, cfg->seed);

    snprintf(c->dir, sizeof c->dir, "%s", cfg->dir);
    c->w.read = cart_read;
    c->w.read_user = c;
    c->w.snd = cfg->snd;
    c->w.snd_user = cfg->snd_user;
    if (cfg->writable) {
        size_t end = 0;
        while (cfg->writable[end]) end += strlen(cfg->writable + end) + 1;
        c->writable = (char *)malloc(end + 1);
        if (c->writable) {
            memcpy(c->writable, cfg->writable, end + 1);
            c->w.writable = c->writable;
        }
    }
    c->files = moy_files_open(cfg->files, cfg->dir);
    if (c->files) moy_files_bind(c->files, &c->w);
    c->lanes = moy_lanes_open(moy_lanes_cores() - 1);
    moy_lanes_bind(c->lanes, &c->w);
    c->w.lane_stack = CART_STACK;
    if (moy_wasm_open(&c->w, &c->con, c->env) != 0) {
        snprintf(err, errlen, "this cart's module is refused: a hook is missing");
        wasm_cart_close(c);
        return NULL;
    }
    return c;
}

int wasm_cart_init(wasm_cart *c, char *err, size_t errlen)
{ return moy_wasm_init(&c->w, err, errlen); }

int wasm_cart_update(wasm_cart *c, float dt, char *err, size_t errlen)
{ return moy_wasm_update(&c->w, dt, err, errlen); }

int wasm_cart_draw(wasm_cart *c, char *err, size_t errlen)
{
    if (c->w.quitting) return 0;
    return moy_wasm_draw(&c->w, err, errlen);
}

void wasm_cart_reset_state(wasm_cart *c) { moy_reset_state(&c->canvas); }

const uint16_t *wasm_cart_frame(const wasm_cart *c) { return c->screen; }

void wasm_cart_close(wasm_cart *c)
{
    if (!c) return;
    moy_wasm_close(&c->w);
    moy_lanes_close(c->lanes);
    moy_files_close(c->files);
    free(c->writable);
    if (c->env) wasm_runtime_destroy_exec_env(c->env);
    if (c->inst) wasm_runtime_deinstantiate(c->inst);
    if (c->module) wasm_runtime_unload(c->module);
    free(c->screen);
    free(c->bytes);
    free(c);
}
