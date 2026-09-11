/* Run a real .moy cart through libmoy + Lua, and dump the frame.
 *
 *   run_cart <cart-dir> <out.bin> [--frames N] [--hold BTN@FROM-TO,...]
 *                                 [--dt SECONDS]
 *   MOY_PROFILE=1 run_cart ...   -- also print a Lua line profile at exit
 *
 * --dt is the frame period handed to _update, 1/30 by default. A host's is
 * whatever its display gives it, and a cart paced from inside (the PICO-8
 * port shim is) behaves differently when a console frame is SHORTER than one
 * cart period -- which the default here never is.
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
#include "../port/moy_manifest.h"

/* -- MOY_PROFILE=1: a Lua line profiler ----------------------------------
 * A count hook samples the running line every PROF_EVERY VM instructions and
 * the report at exit ranks lines and functions by samples, per script.
 *
 * ONE FLAT LINE SPACE ACROSS EVERY SCRIPT (SPEC.md 4): script i's line L is
 * slot prof_base + L, so the per-line arrays stay one-dimensional and a row
 * can still name the file it came from. Without the base, line 25 of a port's
 * shim and line 25 of the game it wraps would be added together -- which is
 * the confusion splitting the files existed to remove. */
#define PROF_EVERY 1000
#define PROF_LINES 16384
static int prof_hits[PROF_LINES];
static int prof_fn[PROF_LINES];
static long prof_total;
static struct prof_chunk {
    const char *name;
    const char *text;
    int base;                       /* slot of this script's line 0 */
    int lines;
    long hits;
} prof_chunk[MOY_SOURCES_MAX];
static int prof_n;

/* Register a script in the flat space. Returns 0 when it does not fit, which
 * only costs the profile -- never the run. */
static int prof_add(const char *name, const char *text)
{
    const char *p;
    int lines = 1, base = 0;
    if (prof_n >= MOY_SOURCES_MAX) return 0;
    for (p = text; *p; p++) if (*p == '\n') lines++;
    if (prof_n) base = prof_chunk[prof_n - 1].base + prof_chunk[prof_n - 1].lines + 1;
    if (base + lines + 1 >= PROF_LINES) return 0;
    prof_chunk[prof_n].name = name;
    prof_chunk[prof_n].text = text;
    prof_chunk[prof_n].base = base;
    prof_chunk[prof_n].lines = lines;
    prof_chunk[prof_n].hits = 0;
    prof_n++;
    return 1;
}

/* The flat slot -> which script, by the highest base at or below it. */
static int prof_owner(int slot)
{
    int i, best = -1;
    for (i = 0; i < prof_n; i++)
        if (prof_chunk[i].base <= slot) best = i;
    return best;
}

static void prof_hook(lua_State *L, lua_Debug *ar)
{
    int i, slot;
    if (!lua_getinfo(L, "Sl", ar) || ar->currentline <= 0) return;
    for (i = 0; i < prof_n; i++)
        if (!strcmp(prof_chunk[i].name, ar->short_src)) break;
    if (i == prof_n) return;                /* not one of the cart's scripts */
    slot = prof_chunk[i].base + ar->currentline;
    if (slot >= PROF_LINES) return;
    prof_total++;
    prof_chunk[i].hits++;
    prof_hits[slot]++;
    prof_fn[slot] = ar->linedefined > 0 ? prof_chunk[i].base + ar->linedefined
                                        : prof_chunk[i].base;
}

/* "name:line", or "name:(main chunk)" for a script's own top level. */
static const char *prof_where(int slot, char *buf, size_t n)
{
    int ci = prof_owner(slot);
    if (ci < 0) { snprintf(buf, n, "?:%d", slot); return buf; }
    if (slot == prof_chunk[ci].base)
        snprintf(buf, n, "%s:(main chunk)", prof_chunk[ci].name);
    else
        snprintf(buf, n, "%s:%d", prof_chunk[ci].name, slot - prof_chunk[ci].base);
    return buf;
}

static const char *prof_line_text(int slot, char *buf, size_t n)
{
    int ci = prof_owner(slot), line;
    const char *p;
    size_t i = 0;
    int l = 1;
    buf[0] = 0;
    if (ci < 0) return buf;
    line = slot - prof_chunk[ci].base;
    if (line <= 0) return buf;
    p = prof_chunk[ci].text;
    while (p && *p && l < line) { if (*p == '\n') l++; p++; }
    if (!p) return buf;
    while (*p == ' ' || *p == '\t') p++;
    while (*p && *p != '\n' && i + 1 < n) buf[i++] = *p++;
    buf[i] = 0;
    return buf;
}

static void prof_report(void)
{
    int fn_hits[PROF_LINES], top[40], i, k, n;
    char text[72], where[80];
    if (!prof_total) return;
    memset(fn_hits, 0, sizeof fn_hits);
    for (i = 1; i < PROF_LINES; i++) {
        if (!prof_hits[i]) continue;
        if (prof_fn[i] >= 0 && prof_fn[i] < PROF_LINES) fn_hits[prof_fn[i]] += prof_hits[i];
    }
    printf("MOY_PROFILE: %ld samples x %d instructions, across %d script%s\n",
           prof_total, PROF_EVERY, prof_n, prof_n == 1 ? "" : "s");
    for (i = 0; i < prof_n; i++)
        printf("   %5.1f%%  %s\n",
               100.0 * (double)prof_chunk[i].hits / (double)prof_total,
               prof_chunk[i].name);
    printf("-- top lines: samples %% where fn | text\n");
    for (n = 0; n < 40; n++) {
        int best = 0;
        for (i = 1; i < PROF_LINES; i++) {
            for (k = 0; k < n; k++) if (top[k] == i) break;
            if (k < n) continue;
            if (prof_hits[i] > prof_hits[best]) best = i;
        }
        if (!best || !prof_hits[best]) break;
        top[n] = best;
        printf("%7d %5.1f%% %-24s | %s\n", prof_hits[best],
               100.0 * (double)prof_hits[best] / (double)prof_total,
               prof_where(best, where, sizeof where),
               prof_line_text(best, text, sizeof text));
    }
    printf("-- top functions (by definition line): samples %% where | text\n");
    for (n = 0; n < 25; n++) {
        int best = -1;
        for (i = 0; i < PROF_LINES; i++) {
            if (!fn_hits[i]) continue;
            for (k = 0; k < n; k++) if (top[k] == i) break;
            if (k < n) continue;
            if (best < 0 || fn_hits[i] > fn_hits[best]) best = i;
        }
        if (best < 0) break;
        top[n] = best;
        printf("%7d %5.1f%% %-24s | %s\n", fn_hits[best],
               100.0 * (double)fn_hits[best] / (double)prof_total,
               prof_where(best, where, sizeof where),
               prof_line_text(best, text, sizeof text));
    }
}

static uint8_t frame[MOY_W * MOY_H];
static uint8_t sheet_pix[MOY_SHEET_W * MOY_SHEET_H];
static uint8_t map_cells[MOY_MAP_MAX * MOY_MAP_MAX];
static uint8_t flag_bytes[MOY_FLAGS];
static uint8_t p8_mem[MOY_P8_MEM];
static uint8_t p8_rom[MOY_P8_ROM];
static moy_p8  p8;
static int32_t pmem_slots[256];
static uint8_t layer_pix[MOY_W * MOY_H];
static int layer_taken;

/* -- the host: what a platform supplies (SPEC.md 7.3, 9) ----------------- */
/* Deterministic on purpose. A conformance frame must not depend on when it was
 * captured, so time stands still and no button is ever held. */

/* SCRIPTED INPUT. `--hold a@30-34,right@90-150` holds a button over a frame
 * range, which is what makes this harness able to answer "does the cart
 * RESPOND" and not only "does it run". Most carts want a button before
 * anything moves at all, so without this a title screen and a dead cart look
 * exactly alike. */
#define HOLD_MAX 16
static struct { moy_button b; int from, to; } holds[HOLD_MAX];
static int n_holds;
static int cur_frame;

static int held_now(moy_button b, int at)
{
    int i;
    for (i = 0; i < n_holds; i++)
        if (holds[i].b == b && at >= holds[i].from && at <= holds[i].to)
            return 1;
    return 0;
}

static int  h_btn(void *u, moy_button b, int p)
{
    (void)u; (void)p;
    return held_now(b, cur_frame);
}

/* Pressed THIS tick: held now and not on the frame before. */
static int  h_btnp(void *u, moy_button b, int p)
{
    (void)u; (void)p;
    return held_now(b, cur_frame) && !held_now(b, cur_frame - 1);
}

static int parse_button(const char *name, moy_button *out)
{
    static const struct { const char *n; moy_button b; } TAB[] = {
        {"left", MOY_BTN_LEFT}, {"right", MOY_BTN_RIGHT},
        {"up", MOY_BTN_UP}, {"down", MOY_BTN_DOWN},
        {"a", MOY_BTN_A}, {"b", MOY_BTN_B}, {"run", MOY_BTN_RUN},
    };
    size_t i;
    for (i = 0; i < sizeof TAB / sizeof TAB[0]; i++)
        if (!strcmp(name, TAB[i].n)) { *out = TAB[i].b; return 1; }
    return 0;
}

/* "a@30-34,right@90-150" */
static int parse_holds(char *spec)
{
    char *item = strtok(spec, ",");
    while (item && n_holds < HOLD_MAX) {
        char name[16];
        int from, to;
        char *at = strchr(item, '@');
        char *dash;
        if (!at) return 0;
        *at = 0;
        if (strlen(item) >= sizeof name) return 0;
        strcpy(name, item);
        dash = strchr(at + 1, '-');
        if (!dash) return 0;
        *dash = 0;
        from = atoi(at + 1);
        to = atoi(dash + 1);
        if (!parse_button(name, &holds[n_holds].b)) return 0;
        holds[n_holds].from = from;
        holds[n_holds].to = to;
        n_holds++;
        item = strtok(NULL, ",");
    }
    return 1;
}
static int  h_players(void *u)                  { (void)u; return 1; }
static uint32_t h_time(void *u)                 { (void)u; return 0; }
static int32_t h_pmem_get(void *u, int s)       { (void)u; return pmem_slots[s]; }
static void h_pmem_set(void *u, int s, int32_t v) { (void)u; pmem_slots[s] = v; }

/* SPEC.md 1.1 guarantees one full-screen layer, so a harness that runs REAL
 * carts has to provide it -- otherwise a conformance cart calling make_layer
 * gets nil here and passes for the wrong reason. A second request declines,
 * which is equally part of the contract. */
static moy_pixel *h_layer_new(void *u, int w, int h)
{
    (void)u;
    if (layer_taken || w <= 0 || h <= 0
        || (size_t)w * (size_t)h > sizeof layer_pix) return NULL;
    layer_taken = 1;
    return layer_pix;
}
static void h_layer_free(void *u, moy_pixel *pix)
{
    (void)u;
    if (pix == layer_pix) layer_taken = 0;
}

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

/* flags.moyflags (SPEC.md 3.5): hex byte pairs in tile order, whitespace
 * ignored, a short or absent file leaves the rest zero. */
static void load_flags(const char *path)
{
    FILE *f = fopen(path, "rb");
    int hi, lo, n = 0;
    if (!f) return;                          /* optional */
    for (;;) {
        do { hi = fgetc(f); } while (hi == '\n' || hi == '\r' || hi == ' ');
        lo = fgetc(f);
        if (hi == EOF || lo == EOF || n >= MOY_FLAGS) break;
        flag_bytes[n++] = (uint8_t)((hexval(hi) << 4) | hexval(lo));
    }
    fclose(f);
}

/* The declared canvas (SPEC.md 3.1): default 320x240, and a value outside the
 * closed set refuses the cart -- running at a size it did not ask for would
 * break every coordinate in it. Returns 0 on an unknown value. */
static int manifest_canvas(const char *dir, int *w, int *h)
{
    char path[1024];
    char *text;
    const char *p;
    int ok = 1;
    *w = MOY_W;
    *h = MOY_H;
    snprintf(path, sizeof path, "%s/manifest.json", dir);
    text = slurp(path, NULL);
    if (!text) return 1;
    p = strstr(text, "\"canvas\"");
    if (p && (p = strchr(p + 8, '"')) != NULL) {
        int cw = 0, ch = 0;
        if (sscanf(p + 1, "%dx%d", &cw, &ch) == 2 &&
            ((cw == 320 && ch == 240) || (cw == 160 && ch == 120) ||
             (cw == 128 && ch == 128))) {
            *w = cw;
            *h = ch;
        } else {
            ok = 0;
        }
    }
    free(text);
    return ok;
}

int main(int argc, char **argv)
{
    moy_canvas canvas;
    moy_sheet sheet;
    moy_map map;
    moy_console con;
    lua_State *L;
    char path[1024], mainfile[MOY_NAME_MAX] = "main.lua", err[512] = {0};
    char srcname[MOY_SOURCES_MAX][MOY_NAME_MAX], chunk[MOY_NAME_MAX + 2];
    char *manifest, *source;
    const char *cart = NULL, *out = NULL;
    int i, frames = 2, cw, ch, nsrc, profiling, keep;
    float dt = 1.0f / 30.0f;

    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--frames") && i + 1 < argc) frames = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--dt") && i + 1 < argc) dt = (float)atof(argv[++i]);
        else if (!strcmp(argv[i], "--hold") && i + 1 < argc) {
            if (!parse_holds(argv[++i])) {
                fprintf(stderr, "run_cart: bad --hold (want "
                                "\"a@30-34,right@90-150\")\n");
                return 2;
            }
        }
        else if (!cart) cart = argv[i];
        else out = argv[i];
    }
    if (!cart || !out) {
        fprintf(stderr, "usage: run_cart <cart-dir> <out.bin> [--frames N]"
                        " [--hold a@30-34,right@90-150] [--dt 0.008]\n");
        return 2;
    }

    if (!manifest_canvas(cart, &cw, &ch)) {
        fprintf(stderr, "run_cart: this cart declares a canvas size this "
                        "player does not have (SPEC.md 3.1)\n");
        return 2;
    }
    moy_canvas_init(&canvas, frame, cw, ch);
    moy_sheet_init(&sheet, sheet_pix);
    moy_map_init(&map, map_cells, 20, 15);
    snprintf(path, sizeof path, "%s/sprites.moygfx", cart);
    load_sheet(path);
    snprintf(path, sizeof path, "%s/map.moymap", cart);
    load_map(path, &map);
    snprintf(path, sizeof path, "%s/flags.moyflags", cart);
    load_flags(path);

    moy_console_init(&con, &canvas, &sheet, &map);
    con.flags = flag_bytes;
    con.host.btn = h_btn;
    con.host.btnp = h_btnp;
    con.host.players = h_players;
    con.host.time_ms = h_time;
    con.host.pmem_get = h_pmem_get;
    con.host.pmem_set = h_pmem_set;
    con.host.quit = h_quit;
    con.host.layer_new = h_layer_new;
    con.host.layer_free = h_layer_free;

    snprintf(path, sizeof path, "%s/manifest.json", cart);
    manifest = slurp(path, NULL);
    moy_manifest_str(manifest, "main", mainfile, sizeof mainfile);
    nsrc = moy_manifest_sources(manifest, mainfile, srcname, MOY_SOURCES_MAX);
    free(manifest);
    if (nsrc < 0) {
        fprintf(stderr, "run_cart: this cart's \"sources\" is not a load order "
                        "this player can follow (SPEC.md 4)\n");
        return 2;
    }

    L = luaL_newstate();
    if (!L) { fprintf(stderr, "run_cart: no lua_State\n"); return 2; }
    moy_lua_open(L, &con);
    moy_p8_open(L, &con, &p8, p8_mem, p8_rom);   /* the PICO-8 machine, for ports */

    profiling = getenv("MOY_PROFILE") != NULL;
    if (profiling) lua_sethook(L, prof_hook, LUA_MASKCOUNT, PROF_EVERY);

    /* SPEC.md 4: every script in `sources`, in order, each as its own chunk --
     * so a `local` in one does not reach the next, and a runtime error names
     * the file it happened in. The chunk name IS the file name for exactly
     * that reason. */
    for (i = 0; i < nsrc; i++) {
        if (snprintf(path, sizeof path, "%s/%s", cart, srcname[i])
                >= (int)sizeof path) {
            fprintf(stderr, "run_cart: cart path too long for %s\n", srcname[i]);
            return 2;
        }
        source = slurp(path, NULL);
        if (!source) {
            fprintf(stderr, "run_cart: cannot read %s\n", path);
            return 2;
        }
        keep = profiling && prof_add(srcname[i], source);
        /* "@name", not "name": the '@' is what makes Lua report `main.lua:3`
         * instead of `[string "main.lua"]:3`, and what makes lua_Debug's
         * short_src the bare file name the profiler matches on. */
        snprintf(chunk, sizeof chunk, "@%.*s", MOY_NAME_MAX - 1, srcname[i]);
        if (luaL_loadbuffer(L, source, strlen(source), chunk) != LUA_OK ||
            lua_pcall(L, 0, 0, 0) != LUA_OK) {
            /* SPEC.md 4.3: report it with the line number, never swallow it. */
            fprintf(stderr, "run_cart: %s\n", lua_tostring(L, -1));
            return 1;
        }
        if (!keep) free(source);
    }

    if (moy_lua_init(L, err, sizeof err)) {
        fprintf(stderr, "run_cart: _init: %s\n", err);
        return 1;
    }
    for (i = 0; i < frames && !quit_requested; i++) {
        cur_frame = i;                  /* what --hold is measured against */
        /* Draw state is per-frame and must not leak (SPEC.md 6). */
        moy_reset_state(&canvas);
        if (moy_lua_update(L, dt, err, sizeof err)) {
            fprintf(stderr, "run_cart: _update: %s\n", err);
            return 1;
        }
        if (moy_lua_draw(L, err, sizeof err)) {
            fprintf(stderr, "run_cart: _draw: %s\n", err);
            return 1;
        }
    }
    lua_close(L);
    prof_report();

    {
        FILE *f = fopen(out, "wb");
        if (!f) { perror(out); return 2; }
        fwrite(frame, 1, (size_t)(cw * ch), f);
        fclose(f);
    }
    return 0;
}
