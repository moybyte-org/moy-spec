/* moy-web -- the browser moy console, as WebAssembly.
 *
 * The third port, and the same shape as the other two: pixels out, buttons in,
 * a clock, persistence. Read port/sdl2/main.c first -- this is that file with a
 * page where the window was, and the differences are only the ones the platform
 * forces.
 *
 * WHAT THE PLATFORM FORCES, and therefore what is worth reading here:
 *
 *   The loop is INVERTED. A browser will not let a program block, so there is
 *   no `while (running)` -- JS owns requestAnimationFrame and calls
 *   moy_web_frame() once per tick. Every entry point below exists because of
 *   that one fact.
 *
 *   The cart arrives as BYTES, not paths. There is no filesystem, so the page
 *   fetches the cart and hands each file over by name (moy_web_file). The
 *   loaders are otherwise the same parsers the other ports use.
 *
 *   Colour resolves HERE, not in JS. 76,800 palette lookups a frame is the one
 *   loop worth keeping on this side of the boundary; the page just uploads the
 *   RGBA the console hands it.
 *
 * WHAT IS NOT DIFFERENT is the important part: the raster, the font, the
 * palette, the sheet, the map, the verb table and the sandbox are libmoy's,
 * identical to the ones an ESP32 links. The browser is a platform like any
 * other, which is the claim this file exists to make good on.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <emscripten.h>

#include "lua.h"
#include "lauxlib.h"

#include "moy.h"
#include "moy_audio.h"

#define KEEP EMSCRIPTEN_KEEPALIVE

/* SPEC.md 8: 44100 is what the synth's own tests run at and what the desktop
 * port opens. The page resamples to whatever its AudioContext actually runs at,
 * continuously, so this number does not have to match anyone's hardware. */
#define AUDIO_RATE 44100
/* One second of headroom. The page asks for what it is short of, never more. */
#define AUDIO_MAX  AUDIO_RATE

static uint8_t  frame[MOY_W * MOY_H];
static uint8_t  sheet_pix[MOY_SHEET_W * MOY_SHEET_H];
static uint8_t  map_cells[MOY_MAP_MAX * MOY_MAP_MAX];
static uint32_t rgba[MOY_W * MOY_H];
static int32_t  pmem_slots[256];

static moy_canvas  canvas;
static moy_sheet   sheet;
static moy_map     map;
static moy_console con;
static moy_bank    bank;
static moy_audio   audio;
static lua_State  *L;

static int cw = MOY_W, ch = MOY_H;
static int fps = 30;
static int running = 0;
static int pmem_dirty = 0;
static char title[128] = "moy";
static char errmsg[512];

/* -- the cart, as named blobs -------------------------------------------- */
/* A page has no filesystem to point at, so it hands the files over one at a
 * time before boot. Small fixed table: a cart is a manifest, a script, and at
 * most a handful of assets (SPEC.md 3). */

#define MAX_FILES 32

typedef struct { char name[64]; char *data; long len; } cart_file;
static cart_file files[MAX_FILES];
static int nfiles = 0;

static void files_clear(void)
{
    int i;
    for (i = 0; i < nfiles; i++) free(files[i].data);
    nfiles = 0;
}

static const char *cart_get(const char *name, long *len)
{
    int i;
    for (i = 0; i < nfiles; i++)
        if (!strcmp(files[i].name, name)) {
            if (len) *len = files[i].len;
            return files[i].data;
        }
    return NULL;
}

/* Called once per cart file before moy_web_boot. `data` is copied: the page is
 * free to reuse its buffer, and a cart that reloads (the dev server's watch)
 * calls moy_web_reset first. */
KEEP int moy_web_file(const char *name, const char *data, int len)
{
    cart_file *f;
    if (nfiles >= MAX_FILES || len < 0) return 1;
    f = &files[nfiles];
    snprintf(f->name, sizeof f->name, "%s", name);
    f->data = malloc((size_t)len + 1);
    if (!f->data) return 1;
    memcpy(f->data, data, (size_t)len);
    f->data[len] = 0;
    f->len = len;
    nfiles++;
    return 0;
}

/* -- asset parsing (SPEC.md 3.2, 3.3) ------------------------------------ */

static int hexval(int c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static void load_sheet(void)
{
    long n = 0, i;
    const char *t = cart_get("sprites.moygfx", &n);
    int x = 0, y = 0;
    memset(sheet_pix, 0, sizeof sheet_pix);
    if (!t) return;                          /* optional (SPEC.md 3) */
    for (i = 0; i < n; i++) {
        int c = (unsigned char)t[i], v;
        if (c == '\n') { if (x) { y++; x = 0; } continue; }
        if (c == '\r') continue;
        v = hexval(c);
        if (v >= 0 && y < MOY_SHEET_H && x < MOY_SHEET_W)
            sheet_pix[y * MOY_SHEET_W + x] = (uint8_t)v;
        x++;
    }
}

static void load_map(void)
{
    long n = 0, i = 0;
    const char *t = cart_get("map.moymap", &n);
    int w = 0, h = 0, y, x;
    memset(map_cells, 0, sizeof map_cells);
    moy_map_init(&map, map_cells, 20, 15);
    if (!t) return;                          /* optional */
    /* "<w> <h>" then w*h hex byte pairs, whitespace-insensitive -- the same
     * grammar the other ports read with fscanf, hand-walked because there is no
     * FILE* here. */
    while (i < n && (t[i] == ' ' || t[i] == '\n' || t[i] == '\r')) i++;
    while (i < n && t[i] >= '0' && t[i] <= '9') w = w * 10 + (t[i++] - '0');
    while (i < n && (t[i] == ' ' || t[i] == '\n' || t[i] == '\r')) i++;
    while (i < n && t[i] >= '0' && t[i] <= '9') h = h * 10 + (t[i++] - '0');
    if (w < 1 || h < 1 || w > MOY_MAP_MAX || h > MOY_MAP_MAX) return;
    for (y = 0; y < h; y++) {
        for (x = 0; x < w; x++) {
            int hi, lo;
            while (i < n && (t[i] == ' ' || t[i] == '\n' || t[i] == '\r')) i++;
            if (i + 1 >= n) { y = h; break; }
            hi = hexval((unsigned char)t[i++]);
            lo = hexval((unsigned char)t[i++]);
            if (hi < 0 || lo < 0) { y = h; break; }
            map_cells[y * w + x] = (uint8_t)((hi << 4) | lo);
        }
    }
    moy_map_init(&map, map_cells, w, h);
}

/* A manifest string field, by minimal scan -- the same deliberate shortcut the
 * other ports take. A production host wants a real parser: it has `extensions`
 * and `runtime` to refuse on (SPEC.md 3.1, 10). */
static void json_str(const char *text, const char *key, char *out, size_t n)
{
    char pat[64];
    const char *p;
    snprintf(pat, sizeof pat, "\"%s\"", key);
    p = text ? strstr(text, pat) : NULL;
    if (p && (p = strchr(p + strlen(pat), '"')) != NULL) {
        const char *s = p + 1, *e = strchr(s, '"');
        if (e && (size_t)(e - s) < n) { memcpy(out, s, (size_t)(e - s)); out[e - s] = 0; }
    }
}

/* -- the host (SPEC.md 7.3, 9) ------------------------------------------- */
/* The page writes into these and the console reads them, which is the whole of
 * the input path: no events cross the boundary, only state. */

static uint8_t held[MOY_BTN_COUNT];
static uint8_t prev[MOY_BTN_COUNT];
static int touch_x, touch_y, touch_down, touch_prev;
static int key_down[256], key_edge[256], key_last;
static int text_mode = 0;
static double now_ms = 0;

static int h_btn(void *u, moy_button b, int player)
{
    (void)u;
    /* SPEC.md 7.3: slot 0 is this console's controls; a higher slot on a
     * one-controller machine is always false, so a two-player cart can ask
     * players() and adapt rather than be refused at load. */
    if (player != 0 || b >= MOY_BTN_COUNT) return 0;
    return held[b];
}

static int h_btnp(void *u, moy_button b, int player)
{
    (void)u;
    if (player != 0 || b >= MOY_BTN_COUNT) return 0;
    return held[b] && !prev[b];              /* SPEC.md 12.2: no autorepeat */
}

static int h_players(void *u) { (void)u; return 1; }
static uint32_t h_time(void *u) { (void)u; return (uint32_t)now_ms; }
static int32_t h_pmem_get(void *u, int s) { (void)u; return pmem_slots[s]; }

static void h_pmem_set(void *u, int s, int32_t v)
{
    (void)u;
    pmem_slots[s] = v;
    /* SPEC.md 9 lets a host defer the write but requires it to land before the
     * cart exits. The page persists to localStorage, which is synchronous and
     * not free, so this marks rather than writes and the loop drains it once a
     * frame. */
    pmem_dirty = 1;
}

static void h_quit(void *u) { (void)u; running = 0; }

/* SPEC.md 7.3: x, y, TAPPED, HELD -- and nil only when the platform has no
 * pointer at all. A browser always has one (mouse, pen or finger), so this
 * always answers; a cart that wants "is anything touching" reads `held`. */
static int h_touch(void *u, int out[4])
{
    (void)u;
    out[0] = touch_x;
    out[1] = touch_y;
    out[2] = touch_down && !touch_prev;      /* the press edge, this tick only */
    out[3] = touch_down;
    return 1;
}

static int h_key(void *u, int code)
{
    (void)u;
    if (code < 0) return key_last;           /* the last typed character */
    return code < 256 ? key_down[code] : 0;
}

static int h_keyp(void *u, int code)
{
    (void)u;
    if (code < 0) return key_last;
    return code < 256 ? key_edge[code] : 0;
}

static void h_textmode(void *u, int on) { (void)u; text_mode = on ? 1 : 0; }

/* SPEC.md 9's config: the author's tuning surface, read by the host because the
 * console never parses JSON. Flat string/number pairs, which is what the format
 * actually holds. The returned pointer is stable until the next call. */
static char cfg_buf[256];

static const char *h_cfg(void *u, const char *key)
{
    const char *text = cart_get("config.json", NULL);
    char pat[80];
    const char *p;
    (void)u;
    if (!text || !key) return NULL;
    snprintf(pat, sizeof pat, "\"%s\"", key);
    p = strstr(text, pat);
    if (!p) return NULL;
    p = strchr(p + strlen(pat), ':');
    if (!p) return NULL;
    p++;
    while (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r') p++;
    if (*p == '"') {
        const char *e = strchr(++p, '"');
        if (!e || (size_t)(e - p) >= sizeof cfg_buf) return NULL;
        memcpy(cfg_buf, p, (size_t)(e - p));
        cfg_buf[e - p] = 0;
    } else {
        size_t i = 0;
        while (i + 1 < sizeof cfg_buf && *p && *p != ',' && *p != '}' &&
               *p != '\n' && *p != ' ') cfg_buf[i++] = *p++;
        cfg_buf[i] = 0;
    }
    return cfg_buf;
}

/* -- audio out (SPEC.md 8) ------------------------------------------------
 *
 * No lock and no callback thread: the page pulls samples from the same thread
 * that runs the frame, between frames, so the synth is never re-entered
 * mid-verb. That is the browser being easier than SDL, not a shortcut. */

static int16_t pcm16[AUDIO_MAX];
static float   pcmf[AUDIO_MAX];
static int     audio_on = 0;
/* Has this cart ever asked for a sound? A browser will not start an
 * AudioContext without a gesture, and the page says so in its status line --
 * but a silent cart must not be nagged to tap for audio it never wanted. */
static int     audio_used = 0;

static void h_sfx(void *u, int n, int chan) { (void)u; audio_used = 1; moy_audio_sfx(&audio, n, chan); }
static void h_beep(void *u, float f, float d) { (void)u; audio_used = 1; moy_audio_beep(&audio, f, d); }
static void h_music(void *u, int t, int loop) { (void)u; audio_used = 1; moy_audio_music(&audio, t, loop); }
static void h_music_stop(void *u) { (void)u; moy_audio_music_stop(&audio); }
static void h_sound_stop(void *u, int c) { (void)u; moy_audio_sound_stop(&audio, c); }
static void h_volume(void *u, int l) { (void)u; moy_audio_volume(&audio, l); }

KEEP int moy_web_audio_wanted(void) { return audio_used; }

/* Render n frames and hand back float32, which is what an AudioWorklet takes.
 * Converting here rather than in JS keeps the per-sample loop in wasm and the
 * page's job a single typed-array copy. */
KEEP float *moy_web_audio(int n)
{
    int i;
    if (!audio_on || n <= 0) return NULL;
    if (n > AUDIO_MAX) n = AUDIO_MAX;
    moy_audio_render(&audio, pcm16, n);
    for (i = 0; i < n; i++) pcmf[i] = (float)pcm16[i] / 32768.0f;
    return pcmf;
}

KEEP int moy_web_audio_rate(void) { return AUDIO_RATE; }

/* -- lifecycle ------------------------------------------------------------ */

KEEP void moy_web_reset(void)
{
    if (L) { lua_close(L); L = NULL; }
    files_clear();
    running = 0;
    errmsg[0] = 0;
    memset(held, 0, sizeof held);
    memset(prev, 0, sizeof prev);
    memset(key_down, 0, sizeof key_down);
    memset(key_edge, 0, sizeof key_edge);
    key_last = 0;
    audio_used = 0;
    touch_x = touch_y = touch_down = touch_prev = 0;
    text_mode = 0;
    now_ms = 0;
}

KEEP const char *moy_web_error(void) { return errmsg; }
KEEP const char *moy_web_title(void) { return title; }
KEEP int moy_web_width(void)  { return cw; }
KEEP int moy_web_height(void) { return ch; }
KEEP int moy_web_fps(void)    { return fps; }
KEEP int moy_web_running(void) { return running; }
KEEP int moy_web_textmode(void) { return text_mode; }
KEEP uint32_t *moy_web_pixels(void) { return rgba; }

/* The framebuffer as SPEC.md 1 indices, which is what a golden frame is. The
 * page never wants this -- it wants the RGBA above -- but conform.mjs writes
 * exactly these bytes, so the browser player is checked by the same suite as
 * every other implementation rather than by a rendering of it. */
KEEP uint8_t *moy_web_indices(void) { return frame; }
/* SPEC.md 9's 256 slots, exposed as memory rather than as verbs: the page loads
 * them from localStorage before boot and writes them back when moy_web_pmem_moved
 * says something changed. Reading 1 KB back and re-encoding it every frame would
 * be a real cost for a value that usually has not moved. */
KEEP int32_t *moy_web_pmem(void) { return pmem_slots; }
KEEP int moy_web_pmem_moved(void) { return pmem_dirty; }
KEEP void moy_web_pmem_clean(void) { pmem_dirty = 0; }

/* Start the cart. Returns 0 on success; on failure the message is in
 * moy_web_error() and the page shows it -- SPEC.md 4.3 wants it reported with
 * the script line number, never swallowed, and a browser console is not a
 * report. */
KEEP int moy_web_boot(uint32_t seed)
{
    const char *manifest = cart_get("manifest.json", NULL);
    const char *source;
    const char *sounds = cart_get("sounds.json", NULL);
    char mainfile[64] = "main.lua", canvas_s[32] = "320x240", runtime_s[32] = "lua";
    long srclen = 0;

    errmsg[0] = 0;
    json_str(manifest, "main", mainfile, sizeof mainfile);
    json_str(manifest, "title", title, sizeof title);
    json_str(manifest, "canvas", canvas_s, sizeof canvas_s);
    json_str(manifest, "runtime", runtime_s, sizeof runtime_s);
    if (strcmp(runtime_s, "lua") != 0) {
        /* SPEC.md 3.1/10: a host refuses what it cannot run rather than
         * guessing. This player has one runtime. */
        snprintf(errmsg, sizeof errmsg,
                 "this cart declares runtime \"%s\"; this player runs lua "
                 "(SPEC.md 3.1)", runtime_s);
        return 1;
    }
    if (manifest) {
        const char *p = strstr(manifest, "\"fps\"");
        fps = 30;
        if (p && (p = strchr(p, ':')) != NULL) fps = atoi(p + 1);
        if (fps != 60) fps = 30;             /* SPEC.md 5: 30 or 60, else 30 */
    }

    /* SPEC.md 3.1: three canvas sizes, a closed set. Running a cart at a size
     * it did not ask for breaks every coordinate in it, so this refuses. */
    if (sscanf(canvas_s, "%dx%d", &cw, &ch) != 2 ||
        !((cw == 320 && ch == 240) || (cw == 160 && ch == 120) ||
          (cw == 128 && ch == 128))) {
        snprintf(errmsg, sizeof errmsg,
                 "this player has no \"%s\" canvas (SPEC.md 3.1)", canvas_s);
        return 1;
    }

    memset(frame, 0, sizeof frame);
    moy_canvas_init(&canvas, frame, cw, ch);
    moy_sheet_init(&sheet, sheet_pix);
    load_sheet();
    load_map();

    if (moy_bank_parse(&bank, sounds))
        /* A malformed bank means silence, not a dead cart (SPEC.md 8.3), but it
         * is worth saying so -- "my music does not play" is otherwise
         * undebuggable. */
        snprintf(errmsg, sizeof errmsg, "sounds.json is malformed; playing silent");

    moy_console_init(&con, &canvas, &sheet, &map);
    con.host.btn = h_btn;
    con.host.btnp = h_btnp;
    con.host.players = h_players;
    con.host.time_ms = h_time;
    con.host.pmem_get = h_pmem_get;
    con.host.pmem_set = h_pmem_set;
    con.host.quit = h_quit;
    con.host.touch = h_touch;
    con.host.key = h_key;
    con.host.keyp = h_keyp;
    con.host.textmode = h_textmode;
    con.host.cfg = h_cfg;
    moy_srand(&con, seed);

    moy_audio_init(&audio, &bank, AUDIO_RATE);
    audio_on = 1;
    con.host.sfx = h_sfx;
    con.host.beep = h_beep;
    con.host.music = h_music;
    con.host.music_stop = h_music_stop;
    con.host.sound_stop = h_sound_stop;
    con.host.volume = h_volume;

    source = cart_get(mainfile, &srclen);
    if (!source) {
        snprintf(errmsg, sizeof errmsg, "cannot read %s", mainfile);
        return 1;
    }

    L = luaL_newstate();
    if (!L) { snprintf(errmsg, sizeof errmsg, "no lua_State"); return 1; }
    moy_lua_open(L, &con);
    if (luaL_loadbuffer(L, source, (size_t)srclen, mainfile) != LUA_OK ||
        lua_pcall(L, 0, 0, 0) != LUA_OK) {
        snprintf(errmsg, sizeof errmsg, "%s", lua_tostring(L, -1));
        lua_close(L);
        L = NULL;
        return 1;
    }
    if (moy_lua_init(L, errmsg, sizeof errmsg)) { lua_close(L); L = NULL; return 1; }
    running = 1;
    return 0;
}

/* -- input ---------------------------------------------------------------- */

KEEP void moy_web_button(int b, int down)
{
    if (b >= 0 && b < MOY_BTN_COUNT) held[b] = down ? 1 : 0;
}

KEEP void moy_web_touch(int x, int y, int down)
{
    touch_x = x;
    touch_y = y;
    touch_down = down ? 1 : 0;
}

KEEP void moy_web_key(int code, int down)
{
    if (code < 0 || code >= 256) return;
    if (down && !key_down[code]) key_edge[code] = 1;
    key_down[code] = down ? 1 : 0;
    if (down) key_last = code;
}

/* -- the frame ------------------------------------------------------------
 *
 * One tick: input edges, update, draw, colour. Returns 0 while the cart is
 * running, 1 if it errored (moy_web_error has the message), 2 if it quit. */
KEEP int moy_web_frame(float dt, double t_ms)
{
    const uint8_t *pal = moy_palette_default;
    int i, n = cw * ch;

    if (!running || !L) return running ? 1 : 2;
    now_ms = t_ms;
    /* SPEC.md 5: dt is real elapsed time, so speed * dt is right at any rate.
     * Clamped so a backgrounded tab does not teleport everything on return. */
    if (dt > 0.25f) dt = 0.25f;
    if (dt < 0.0f) dt = 0.0f;

    moy_reset_state(&canvas);                /* draw state is per-frame (6) */
    if (moy_lua_update(L, dt, errmsg, sizeof errmsg)) { running = 0; return 1; }
    if (moy_lua_draw(L, errmsg, sizeof errmsg))       { running = 0; return 1; }

    /* The btnp, key and tap edges are latched for exactly one tick, and cleared
     * AFTER the cart has seen them -- clearing on the way in would race a press
     * that arrived between frames and drop it entirely. */
    for (i = 0; i < MOY_BTN_COUNT; i++) prev[i] = held[i];
    memset(key_edge, 0, sizeof key_edge);
    touch_prev = touch_down;

    /* pixels out: the one place the console's colours become anyone else's.
     * Little-endian RGBA, which is what an ImageData wants byte for byte. */
    for (i = 0; i < n; i++) {
        const uint8_t *e = pal + (size_t)frame[i] * 3;
        rgba[i] = 0xFF000000u | ((uint32_t)e[2] << 16) | ((uint32_t)e[1] << 8) | e[0];
    }
    if (!running) return 2;
    return 0;
}

/* Emscripten wants an entry point; the loop belongs to the page. */
int main(void) { return 0; }
