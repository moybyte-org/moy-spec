/* Run a real .moy cart through libmoy + Lua, and dump the frame.
 *
 *   run_cart <cart-dir> <out.bin> [--frames N]
 *
 * Speaks the conformance player protocol, so
 *
 *   python3 conformance/run.py --player "libmoy/build/run_cart {cart} {out}"
 *
 * checks libmoy the way a FINISHED HOST is checked: the cart's own Lua is
 * parsed and executed, the sandbox is in force, the verb table is exercised
 * through the binding. trace_replay checks the raster; this checks the
 * console. Both matter, and they fail differently -- a raster bug shows up in
 * both, a binding bug only here.
 *
 * This is a test harness, not a host. A host also refuses unimplemented
 * `runtime` and `extensions` values (SPEC.md 3.1, 10), honours a cart-supplied
 * palette (2.2), and enforces the tick model (5). Those are host policy and
 * moycore models them; what is exercised here is libmoy.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "lua.h"
#include "lauxlib.h"

#include "moy.h"

static uint8_t frame[MOY_W * MOY_H];
static uint8_t sheet_pix[MOY_SHEET_W * MOY_SHEET_H];
static uint8_t map_cells[MOY_MAP_MAX * MOY_MAP_MAX];
static int32_t pmem_slots[256];

/* -- the host: what a platform supplies (SPEC.md 7.3, 9) ----------------- */
/* Deterministic on purpose. A conformance frame must not depend on when it was
 * captured, so time stands still and no button is ever held. */

static int  h_btn(void *u, moy_button b, int p) { (void)u; (void)b; (void)p; return 0; }
static int  h_players(void *u)                  { (void)u; return 1; }
static uint32_t h_time(void *u)                 { (void)u; return 0; }
static int32_t h_pmem_get(void *u, int s)       { (void)u; return pmem_slots[s]; }
static void h_pmem_set(void *u, int s, int32_t v) { (void)u; pmem_slots[s] = v; }

static int quit_requested = 0;
static void h_quit(void *u) { (void)u; quit_requested = 1; }

/* -- assets -------------------------------------------------------------- */

static int hexval(int ch)
{
    if (ch >= '0' && ch <= '9') return ch - '0';
    if (ch >= 'a' && ch <= 'f') return ch - 'a' + 10;
    if (ch >= 'A' && ch <= 'F') return ch - 'A' + 10;
    return -1;
}

static char *slurp(const char *path, long *size_out)
{
    FILE *f = fopen(path, "rb");
    char *buf;
    long size;
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    size = ftell(f);
    fseek(f, 0, SEEK_SET);
    buf = malloc((size_t)size + 1);
    if (!buf || fread(buf, 1, (size_t)size, f) != (size_t)size) {
        fclose(f);
        free(buf);
        return NULL;
    }
    buf[size] = 0;
    fclose(f);
    if (size_out) *size_out = size;
    return buf;
}

static void load_sheet(const char *path)
{
    long n;
    char *text = slurp(path, &n);
    int x = 0, y = 0;
    long i;
    if (!text) return;                       /* optional (SPEC.md 3) */
    for (i = 0; i < n; i++) {
        int ch = (unsigned char)text[i], v;
        if (ch == '\n') { if (x) { y++; x = 0; } continue; }
        if (ch == '\r') continue;
        v = hexval(ch);
        if (v >= 0 && y < MOY_SHEET_H && x < MOY_SHEET_W)
            sheet_pix[y * MOY_SHEET_W + x] = (uint8_t)v;
        x++;
    }
    free(text);
}

static void load_map(const char *path, moy_map *m)
{
    FILE *f = fopen(path, "rb");
    int w = 0, h = 0, y, x;
    if (!f) return;                          /* optional */
    if (fscanf(f, "%d %d", &w, &h) != 2 ||
        w < 1 || h < 1 || w > MOY_MAP_MAX || h > MOY_MAP_MAX) {
        fclose(f);
        return;
    }
    for (y = 0; y < h; y++) {
        for (x = 0; x < w; x++) {
            int hi, lo;
            do { hi = fgetc(f); } while (hi == '\n' || hi == '\r' || hi == ' ');
            lo = fgetc(f);
            if (hi == EOF || lo == EOF) { y = h; break; }
            map_cells[y * w + x] = (uint8_t)((hexval(hi) << 4) | hexval(lo));
        }
    }
    fclose(f);
    moy_map_init(m, map_cells, w, h);
}

/* The manifest's `main` (SPEC.md 3.1), by a deliberately minimal scan rather
 * than a JSON parser: a host has one already, and this needs one field. */
static void manifest_main(const char *dir, char *out, size_t outlen)
{
    char path[1024];
    char *text;
    const char *p;
    snprintf(out, outlen, "main.lua");
    snprintf(path, sizeof path, "%s/manifest.json", dir);
    text = slurp(path, NULL);
    if (!text) return;
    p = strstr(text, "\"main\"");
    /* One strchr past the key finds the value's OPENING quote; a second would
     * land on its closing one and yield the comma after it. */
    if (p && (p = strchr(p + 6, '"')) != NULL) {
        const char *start = p + 1, *end = strchr(start, '"');
        if (end && (size_t)(end - start) < outlen) {
            memcpy(out, start, (size_t)(end - start));
            out[end - start] = 0;
        }
    }
    free(text);
}

int main(int argc, char **argv)
{
    moy_canvas canvas;
    moy_sheet sheet;
    moy_map map;
    moy_console con;
    lua_State *L;
    char path[1024], mainfile[256], err[512] = {0};
    char *source;
    const char *cart = NULL, *out = NULL;
    int i, frames = 2;

    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--frames") && i + 1 < argc) frames = atoi(argv[++i]);
        else if (!cart) cart = argv[i];
        else out = argv[i];
    }
    if (!cart || !out) {
        fprintf(stderr, "usage: run_cart <cart-dir> <out.bin> [--frames N]\n");
        return 2;
    }

    moy_canvas_init(&canvas, frame, MOY_W, MOY_H);
    moy_sheet_init(&sheet, sheet_pix);
    moy_map_init(&map, map_cells, 20, 15);
    snprintf(path, sizeof path, "%s/sprites.moygfx", cart);
    load_sheet(path);
    snprintf(path, sizeof path, "%s/map.moymap", cart);
    load_map(path, &map);

    moy_console_init(&con, &canvas, &sheet, &map);
    con.host.btn = h_btn;
    con.host.btnp = h_btn;
    con.host.players = h_players;
    con.host.time_ms = h_time;
    con.host.pmem_get = h_pmem_get;
    con.host.pmem_set = h_pmem_set;
    con.host.quit = h_quit;

    manifest_main(cart, mainfile, sizeof mainfile);
    snprintf(path, sizeof path, "%s/%s", cart, mainfile);
    source = slurp(path, NULL);
    if (!source) {
        fprintf(stderr, "run_cart: cannot read %s\n", path);
        return 2;
    }

    L = luaL_newstate();
    if (!L) { fprintf(stderr, "run_cart: no lua_State\n"); return 2; }
    moy_lua_open(L, &con);

    if (luaL_loadbuffer(L, source, strlen(source), mainfile) != LUA_OK ||
        lua_pcall(L, 0, 0, 0) != LUA_OK) {
        /* SPEC.md 4.3: report it with the script line number, never swallow it. */
        fprintf(stderr, "run_cart: %s\n", lua_tostring(L, -1));
        return 1;
    }
    free(source);

    if (moy_lua_init(L, err, sizeof err)) {
        fprintf(stderr, "run_cart: _init: %s\n", err);
        return 1;
    }
    for (i = 0; i < frames && !quit_requested; i++) {
        /* Draw state is per-frame and must not leak (SPEC.md 6). */
        moy_reset_state(&canvas);
        if (moy_lua_update(L, 1.0f / 30.0f, err, sizeof err)) {
            fprintf(stderr, "run_cart: _update: %s\n", err);
            return 1;
        }
        if (moy_lua_draw(L, err, sizeof err)) {
            fprintf(stderr, "run_cart: _draw: %s\n", err);
            return 1;
        }
    }
    lua_close(L);

    {
        FILE *f = fopen(out, "wb");
        if (!f) { perror(out); return 2; }
        fwrite(frame, 1, sizeof frame, f);
        fclose(f);
    }
    return 0;
}
