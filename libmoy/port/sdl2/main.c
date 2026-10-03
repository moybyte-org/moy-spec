/* moy-play -- a desktop moy console in SDL2, and the porting layer as a
 * worked example.
 *
 *   moy-play <cart.moy> [--scale N] [--fullscreen] [--watch] [--files DIR]
 *   moy-play <cart.moy> --dump <out> [--frames N] [--cover] [--files DIR]
 *   moy-play --runtimes
 *
 * READ TO THE "hot reload" COMMENT AND STOP. Everything above it -- under
 * three hundred lines -- is the whole of what this platform owes the console,
 * and is the part worth copying. Everything below it watches the cart folder
 * and rebuilds the Lua state when a file changes, which is a convenience for
 * whoever is WRITING the cart and no part of running one. It is off unless
 * --watch asks for it, which is why a cart that errors still ends the way
 * SPEC.md 4.3 says it must: the player exits. `moy play` passes the flag.
 *
 * The claim libmoy makes is that adopting moy costs a platform shim, not a
 * project; this file is that shim for one platform, and it is the whole of it.
 * Read it before writing yours -- the ESP-IDF one is the same shape with
 * different names, and there is nothing else to implement.
 *
 * What a platform actually owes the console (SPEC.md 0 is emphatic that the
 * rest is not the spec's business):
 *
 *   pixels out    resolve the index framebuffer through the palette and put it
 *                 on the glass, however your glass works
 *   buttons in    map your hardware onto SPEC.md 7.3's seven logical buttons
 *   a clock       milliseconds, for time() and for the tick
 *   persistence   256 signed 32-bit slots, if you have anywhere to put them
 *
 * That is it. Audio is optional (SPEC.md 8.3: silence is a valid rendering) --
 * but this port has it, and the whole of it is the ~50 lines below marked
 * "audio out": libmoy's moy_audio module is the synthesizer, the port only
 * opens a device and pumps the render call. A host that skips those lines is
 * still conforming, just mute. Everything else -- the raster, the palette, the
 * font, the sheet, the map, the verb table, the sandbox -- is libmoy's.
 *
 * A "runtime": "wasm" cart (SPEC.md 16) runs through the same
 * hooks on libmoy's wasm binding, in wasm_cart.c, when the player is built
 * with MOY_PLAY_WASM; without it such a cart is refused cleanly (SPEC.md
 * 3.1). --memory-limit MIB caps what a compiled cart may take to load.
 *
 * A compiled cart's written files (SPEC.md 16.12) are kept per cart in moy's
 * per-user data folder, files/<cart>: <cart> is the cart folder's name less
 * ".moy", so a rebuilt or reinstalled cart finds its files again. That folder
 * is outside the cart's, and the player removes nothing in it: a cart here is
 * a folder, and deleting one is not something the player sees. --files DIR
 * keeps them in DIR instead.
 *
 * A compiled cart's sample stream (`snd`) is mixed into the same output as the
 * synth, after it; when the cart made one, the player says on exit how many
 * frames the cart queued and the output played, over how long.
 *
 * --dump is the conformance player (SPEC.md 11, conformance/wasm_run.py): no
 * window, no audio, the clock stopped and rnd() seeded 0, and after the ticks
 * the last frame the cart finished is written to <out> -- palette indices for
 * a Lua cart, RGB565 little-endian for a compiled one -- or, with --cover, as
 * the cover.png F7 would write for it. It keeps no written files unless
 * --files names a folder for them.
 *
 * F7, with --watch, writes the frame on screen as the cart's cover.png
 * (SPEC.md 3.6); see "the cover" below.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include <SDL2/SDL.h>

#include "lua.h"
#include "lauxlib.h"

#include "moy.h"
#include "moy_audio.h"
#include "../moy_manifest.h"
#ifdef MOY_PLAY_WASM
#include "wasm_cart.h"
#endif

/* The cart's own 64-colour table (SPEC.md 2.2), when it ships one: these
 * loaders resolve an index to a colour themselves, so a cart palette has to
 * reach the pixel-out path or it may as well not be in the manifest. */
static unsigned char cart_pal[64 * 3];
static int cart_pal_ok;

static uint8_t  frame[MOY_W * MOY_H];
static uint8_t  sheet_pix[MOY_SHEET_W * MOY_SHEET_H];
static uint8_t  map_cells[MOY_MAP_MAX * MOY_MAP_MAX];
static uint32_t pixels[MOY_W * MOY_H];          /* ARGB8888 for the texture */
static int32_t  pmem_slots[256];
static char     pmem_path[1024];
/* A compiled cart's writable paths, in moy_wasm's form, and the folder its
 * written files are kept in (empty: none are kept). */
static char     writable[1024];
static char     files_at[1024];

/* -- the host (SPEC.md 7.3, 9) ------------------------------------------- */

typedef struct {
    const uint8_t *keys;        /* SDL's keyboard state, refreshed per frame */
    uint8_t held[MOY_BTN_COUNT];
    uint8_t prev[MOY_BTN_COUNT];
    uint32_t t0;
    int frozen;                 /* --dump: time() stands at 0 */
    int running;
    /* SPEC.md 6 view/background state. view_w = 0 means the cart has not
     * declared a region, so the whole canvas presents. */
    int view_w, view_h;
    int bg, has_bg;
} host_state;

/* One physical key per logical button, plus the arrows. A real handheld maps
 * its d-pad here instead; that a keyboard and a d-pad both work, unchanged, is
 * exactly what SPEC.md 7.3 means by "logical". */
static const SDL_Scancode KEYMAP[MOY_BTN_COUNT][2] = {
    {SDL_SCANCODE_LEFT,  SDL_SCANCODE_A},
    {SDL_SCANCODE_RIGHT, SDL_SCANCODE_D},
    {SDL_SCANCODE_UP,    SDL_SCANCODE_W},
    {SDL_SCANCODE_DOWN,  SDL_SCANCODE_S},
    {SDL_SCANCODE_Z,     SDL_SCANCODE_J},
    {SDL_SCANCODE_X,     SDL_SCANCODE_K},
    {SDL_SCANCODE_RETURN, SDL_SCANCODE_SPACE},
};

static int h_btn(void *u, moy_button b, int player)
{
    host_state *h = (host_state *)u;
    /* SPEC.md 7.3: slot 0 is this console's own controls; a higher slot on a
     * one-controller machine is always false, which is what lets a two-player
     * cart ask players() and adapt instead of being refused at load. */
    if (player != 0 || b >= MOY_BTN_COUNT) return 0;
    return h->held[b];
}

static int h_btnp(void *u, moy_button b, int player)
{
    host_state *h = (host_state *)u;
    if (player != 0 || b >= MOY_BTN_COUNT) return 0;
    /* A real released->held edge, latched once per tick: SPEC.md 12.2 gives
     * btnp no autorepeat, and a cart wanting repeat writes its own timer. */
    return h->held[b] && !h->prev[b];
}

/* SPEC.md 1.1 guarantees a cart one full-screen layer, and a desktop has no
 * reason to stop at one: the 75 KB constrains a handheld, not a PC. Only the
 * SECOND and later requests are a host's to refuse, and this one does not. */
static moy_pixel *h_layer_new(void *u, int w, int h)
{
    (void)u;
    return (moy_pixel *)calloc((size_t)w * (size_t)h, sizeof(moy_pixel));
}

static void h_layer_free(void *u, moy_pixel *pix) { (void)u; free(pix); }

static void h_view(void *u, int w, int h)
{
    host_state *hs = (host_state *)u;
    hs->view_w = w > 0 ? w : 0;
    hs->view_h = h > 0 ? h : 0;
}

static void h_background(void *u, int col)
{
    host_state *hs = (host_state *)u;
    hs->bg = col;
    hs->has_bg = 1;
}

static int      h_players(void *u) { (void)u; return 1; }
static uint32_t h_time(void *u)
{
    host_state *h = (host_state *)u;
    return h->frozen ? 0 : SDL_GetTicks() - h->t0;
}
static int32_t  h_pmem_get(void *u, int s) { (void)u; return pmem_slots[s]; }

static void h_pmem_set(void *u, int s, int32_t v)
{
    (void)u;
    pmem_slots[s] = v;
    /* SPEC.md 9 lets a host defer the write but requires it to land before the
     * cart exits. Writing through is the simplest way to be correct, and 1 KB
     * is not worth a dirty flag. */
    if (pmem_path[0]) {
        FILE *f = fopen(pmem_path, "wb");
        if (f) { fwrite(pmem_slots, sizeof pmem_slots, 1, f); fclose(f); }
    }
}

static void h_quit(void *u) { ((host_state *)u)->running = 0; }

/* -- audio out (SPEC.md 8) ------------------------------------------------
 *
 * The synth is libmoy's (moy_audio); this is the plumbing: SDL pulls samples
 * on its own thread, so every verb that mutates synth state locks the device
 * around the call. That lock IS the thread-safety story -- moy_audio itself
 * is single-threaded on purpose. */

static moy_bank  bank;
static moy_audio audio;
static SDL_AudioDeviceID adev;

#ifdef MOY_PLAY_WASM
/* A compiled cart's `snd`: its frames queue here and the callback adds them
 * after the synth, at the stream's own rate whatever the device's. */
static moy_stream pcm;
static int16_t pcm_ring[WASM_CART_SND_DEPTH];
static uint32_t pcm_t0;                        /* when the first frame queued */

static uint32_t h_snd(void *u, const uint8_t *frames, uint32_t n)
{
    uint32_t r;
    (void)u;
    SDL_LockAudioDevice(adev);
    r = n ? moy_stream_write(&pcm, frames, n) : moy_stream_room(&pcm);
    if (n && r && !pcm_t0) pcm_t0 = SDL_GetTicks() | 1u;
    SDL_UnlockAudioDevice(adev);
    return r;
}

static void pcm_reset(void)
{
    if (adev) SDL_LockAudioDevice(adev);
    moy_stream_init(&pcm, pcm_ring, WASM_CART_SND_DEPTH, WASM_CART_SND_RATE);
    pcm_t0 = 0;
    if (adev) SDL_UnlockAudioDevice(adev);
}

/* What the stream did, measured from both ends: the frames the cart queued,
 * the frames the output played and how often it found none. */
static void pcm_report(void)
{
    uint32_t ms;
    if (!pcm.in) return;
    SDL_LockAudioDevice(adev);
    ms = SDL_GetTicks() - pcm_t0;
    fprintf(stderr, "moy-play: snd: %u frames queued, %u played, %u starved, "
                    "over %.1f s: %.0f played a second\n",
            (unsigned)pcm.in, (unsigned)pcm.out, (unsigned)pcm.starved,
            (double)ms / 1000.0, ms ? (double)pcm.out * 1000.0 / (double)ms : 0.0);
    SDL_UnlockAudioDevice(adev);
}
#endif

static void audio_cb(void *ud, Uint8 *stream, int len)
{
    (void)ud;
    moy_audio_render(&audio, (int16_t *)(void *)stream, len / 2);
#ifdef MOY_PLAY_WASM
    moy_stream_mix(&pcm, (int16_t *)(void *)stream, len / 2, audio.rate, audio.master);
#endif
}

static void h_sfx(void *u, int n, int chan)
{
    (void)u;
    SDL_LockAudioDevice(adev);
    moy_audio_sfx(&audio, n, chan);
    SDL_UnlockAudioDevice(adev);
}

static void h_beep(void *u, float freq, float dur)
{
    (void)u;
    SDL_LockAudioDevice(adev);
    moy_audio_beep(&audio, freq, dur);
    SDL_UnlockAudioDevice(adev);
}

static void h_music(void *u, int track, int loop)
{
    (void)u;
    SDL_LockAudioDevice(adev);
    moy_audio_music(&audio, track, loop);
    SDL_UnlockAudioDevice(adev);
}

static void h_music_stop(void *u)
{
    (void)u;
    SDL_LockAudioDevice(adev);
    moy_audio_music_stop(&audio);
    SDL_UnlockAudioDevice(adev);
}

static void h_sound_stop(void *u, int chan)
{
    (void)u;
    SDL_LockAudioDevice(adev);
    moy_audio_sound_stop(&audio, chan);
    SDL_UnlockAudioDevice(adev);
}

static void h_volume(void *u, int level)
{
    (void)u;
    SDL_LockAudioDevice(adev);
    moy_audio_volume(&audio, level);
    SDL_UnlockAudioDevice(adev);
}

/* -- cart loading -------------------------------------------------------- */

static int hexval(int c)
{
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    if (c >= 'A' && c <= 'F') return c - 'A' + 10;
    return -1;
}

static char *slurp(const char *path, long *n)
{
    FILE *f = fopen(path, "rb");
    char *b;
    long size;
    if (!f) return NULL;
    fseek(f, 0, SEEK_END); size = ftell(f); fseek(f, 0, SEEK_SET);
    b = malloc((size_t)size + 1);
    if (!b || fread(b, 1, (size_t)size, f) != (size_t)size) { fclose(f); free(b); return NULL; }
    b[size] = 0;
    fclose(f);
    if (n) *n = size;
    return b;
}

static void load_sheet(const char *dir)
{
    char path[1024];
    long n, i;
    char *t;
    int x = 0, y = 0;
    snprintf(path, sizeof path, "%s/sprites.moygfx", dir);
    t = slurp(path, &n);
    if (!t) return;
    for (i = 0; i < n; i++) {
        int c = (unsigned char)t[i], v;
        if (c == '\n') { if (x) { y++; x = 0; } continue; }
        if (c == '\r') continue;
        v = hexval(c);
        if (v >= 0 && y < MOY_SHEET_H && x < MOY_SHEET_W)
            sheet_pix[y * MOY_SHEET_W + x] = (uint8_t)v;
        x++;
    }
    free(t);
}

static uint8_t flag_bytes[MOY_FLAGS];
static uint8_t p8_mem[MOY_P8_MEM];
static uint8_t p8_rom[MOY_P8_ROM];
static moy_p8  p8;

/* flags.moyflags (SPEC.md 3.5): hex byte pairs in tile order, whitespace
 * ignored, absent or short leaves the rest zero. */
static void load_flags(const char *dir)
{
    char path[1024];
    FILE *f;
    int hi, lo, n = 0;
    memset(flag_bytes, 0, sizeof flag_bytes);
    snprintf(path, sizeof path, "%s/flags.moyflags", dir);
    f = fopen(path, "rb");
    if (!f) return;
    for (;;) {
        do { hi = fgetc(f); } while (hi == '\n' || hi == '\r' || hi == ' ');
        lo = fgetc(f);
        if (hi == EOF || lo == EOF || n >= MOY_FLAGS) break;
        flag_bytes[n++] = (uint8_t)((hexval(hi) << 4) | hexval(lo));
    }
    fclose(f);
}

static void load_map(const char *dir, moy_map *m)
{
    char path[1024];
    FILE *f;
    int w = 0, h = 0, y, x;
    snprintf(path, sizeof path, "%s/map.moymap", dir);
    f = fopen(path, "rb");
    if (!f) return;
    if (fscanf(f, "%d %d", &w, &h) != 2 ||
        w < 1 || h < 1 || w > MOY_MAP_MAX || h > MOY_MAP_MAX) { fclose(f); return; }
    for (y = 0; y < h; y++)
        for (x = 0; x < w; x++) {
            int hi, lo;
            do { hi = fgetc(f); } while (hi == '\n' || hi == '\r' || hi == ' ');
            lo = fgetc(f);
            if (hi == EOF || lo == EOF) { y = h; break; }
            map_cells[y * w + x] = (uint8_t)((hexval(hi) << 4) | hexval(lo));
        }
    fclose(f);
    moy_map_init(m, map_cells, w, h);
}

/* SPEC.md 4: run every script in `sources`, in order, each as its own chunk --
 * so a `local` in one does not reach the next, and 4.3's line number names the
 * file it counts from. Used by boot AND by the reload below, because a load
 * order that differs between the two is a bug you only meet mid-edit. */
static int load_sources(lua_State *L, const char *dir,
                        char src[][MOY_NAME_MAX], int n, char *err, size_t errn)
{
    int i;
    for (i = 0; i < n; i++) {
        char path[1024], chunk[MOY_NAME_MAX + 2];
        char *text;
        if (snprintf(path, sizeof path, "%s/%s", dir, src[i]) >= (int)sizeof path) {
            snprintf(err, errn, "cart path too long for %s", src[i]);
            return 1;
        }
        text = slurp(path, NULL);
        if (!text) { snprintf(err, errn, "cannot read %.400s", path); return 1; }
        /* "@name" so Lua reports `main.lua:3`, not `[string "main.lua"]:3`. */
        snprintf(chunk, sizeof chunk, "@%.*s", MOY_NAME_MAX - 1, src[i]);
        if (luaL_loadbuffer(L, text, strlen(text), chunk) != LUA_OK ||
            lua_pcall(L, 0, 0, 0) != LUA_OK) {
            snprintf(err, errn, "%s", lua_tostring(L, -1));
            free(text);
            return 1;
        }
        free(text);
    }
    return 0;
}

/* -- hot reload ----------------------------------------------------------
 *
 * NOT part of what a platform owes the console. Everything above this comment
 * is the porting shim; an implementer copying this file should read to here
 * and stop, because a console in somebody's hand does not watch a folder. It
 * is here because `moy play` is the loop a cart author lives in -- edit
 * main.lua, see the change -- and that loop used to require a browser.
 *
 * It HASHES the cart's files rather than stat-ing their mtimes: no clock, no
 * platform header, no granularity to get wrong, and a save that rewrites the
 * same bytes does nothing, which is right. `.pmem` is deliberately not in the
 * list -- that is the cart's save file, and watching it would reload the cart
 * every time the game saved.
 */
#define WATCH_MS 400

static uint64_t fnv1a(uint64_t h, const void *p, size_t n)
{
    const unsigned char *b = (const unsigned char *)p;
    while (n--) { h ^= (uint64_t)*b++; h *= 1099511628211ull; }
    return h;
}

static uint64_t cart_stamp(const char *dir, char src[][MOY_NAME_MAX], int nsrc)
{
    static const char *const also[] = {
        "manifest.json", "sprites.moygfx", "map.moymap",
        "sounds.json", "config.json"
    };
    uint64_t h = 14695981039346656037ull;
    size_t k, nfixed = sizeof also / sizeof *also;
    /* EVERY script (SPEC.md 4), not just main: a cart whose shim lives in its
     * own file is one whose shim you also want to edit and see. manifest.json
     * is in the list, so a change to `sources` itself is caught too. */
    for (k = 0; k < nfixed + (size_t)nsrc; k++) {
        char path[1024];
        long n = 0;
        char *t;
        const char *name = k < nfixed ? also[k] : src[k - nfixed];
        snprintf(path, sizeof path, "%s/%.*s", dir, MOY_NAME_MAX - 1, name);
        t = slurp(path, &n);
        if (t) { h = fnv1a(h, t, (size_t)n); free(t); }
        h = fnv1a(h, "|", 1);       /* a file appearing or vanishing counts */
    }
    return h;
}

/* -- the cart's runtime ---------------------------------------------------
 *
 * A Lua cart runs on vm and the index canvas; a compiled one on wc and its own
 * direct-colour screen. Everything from here down calls these and does not
 * care which. */

static lua_State *vm;
static int is_wasm;
#ifdef MOY_PLAY_WASM
static wasm_cart *wc;
#endif

static int cart_init(char *err, size_t n)
{
#ifdef MOY_PLAY_WASM
    if (is_wasm) return wasm_cart_init(wc, err, n);
#endif
    return moy_lua_init(vm, err, n);
}

static void cart_reset_state(moy_canvas *canvas)
{
#ifdef MOY_PLAY_WASM
    if (is_wasm) { wasm_cart_reset_state(wc); return; }
#endif
    moy_reset_state(canvas);
}

static int cart_update(float dt, char *err, size_t n)
{
#ifdef MOY_PLAY_WASM
    if (is_wasm) return wasm_cart_update(wc, dt, err, n);
#endif
    return moy_lua_update(vm, dt, err, n);
}

/* SPEC.md 6: background(x) declares a backdrop the host repaints before each
 * _draw, so a cart that has one need not cls() itself. The wasm binding
 * repaints its own screen; the Lua one leaves it to the host. */
static int cart_draw(moy_canvas *canvas, const host_state *hs, char *err, size_t n)
{
#ifdef MOY_PLAY_WASM
    if (is_wasm) return wasm_cart_draw(wc, err, n);
#endif
    if (hs->has_bg) moy_cls(canvas, hs->bg);
    return moy_lua_draw(vm, err, n);
}

/* pixels out: the one place the console's colours become anyone's. The
 * canvas already holds the frame as shown (SPEC.md 6); a compiled cart's
 * screen holds RGB565, widened here by repeating each channel's high bits. */
static void present(int cw, int ch)
{
    int p;
#ifdef MOY_PLAY_WASM
    if (is_wasm) {
        const uint16_t *px = wasm_cart_frame(wc);
        for (p = 0; p < cw * ch; p++) {
            uint32_t v = px[p], r = v >> 11, g = (v >> 5) & 63u, b = v & 31u;
            pixels[p] = 0xFF000000u | (((r << 3) | (r >> 2)) << 16)
                      | (((g << 2) | (g >> 4)) << 8) | ((b << 3) | (b >> 2));
        }
        return;
    }
#endif
    {
        const uint8_t *pal = cart_pal_ok ? cart_pal : moy_palette_default;
        for (p = 0; p < cw * ch; p++) {
            const uint8_t *e = pal + (size_t)frame[p] * 3;
            pixels[p] = 0xFF000000u | ((uint32_t)e[0] << 16) | ((uint32_t)e[1] << 8) | e[2];
        }
    }
}

/* Boot the cart in `cart`: its scripts on a fresh vm, or its module in a fresh
 * wc. Nothing already running is touched until the new one has loaded, which
 * is what lets a failed reload leave the previous cart where it was. 0, or 1
 * with the reason in `err`. */
static int cart_boot(const char *cart, const char *mainfile,
                     char src[][MOY_NAME_MAX], int nsrc, long pages, int cw, int ch,
                     moy_console *con, uint32_t seed, uint64_t limit,
                     char *err, size_t n)
{
#ifdef MOY_PLAY_WASM
    if (is_wasm) {
        wasm_cart_config cfg;
        wasm_cart *next;
        memset(&cfg, 0, sizeof cfg);
        cfg.dir = cart;
        cfg.main = mainfile;
        cfg.pages = (uint32_t)pages;
        cfg.w = cw;
        cfg.h = ch;
        cfg.palette = cart_pal_ok ? cart_pal : NULL;
        cfg.sheet = sheet_pix;
        cfg.cells = con->map->cells;
        cfg.map_w = con->map->w;
        cfg.map_h = con->map->h;
        cfg.flags = flag_bytes;
        cfg.host = &con->host;
        cfg.seed = seed;
        cfg.limit = limit;
        cfg.writable = writable;
        cfg.files = files_at[0] ? files_at : NULL;
        if (adev) {
            cfg.snd = h_snd;
            pcm_reset();
        }
        next = wasm_cart_open(&cfg, err, n);
        if (!next) return 1;
        if (wc) wasm_cart_close(wc);
        wc = next;
        return 0;
    }
#else
    (void)mainfile; (void)pages; (void)cw; (void)ch; (void)seed; (void)limit;
#endif
    {
        lua_State *nl = luaL_newstate();
        moy_lua_open(nl, con);
        moy_p8_open(nl, con, &p8, p8_mem, p8_rom);   /* the PICO-8 machine, for ports */
        if (load_sources(nl, cart, src, nsrc, err, n)) {
            lua_close(nl);
            return 1;
        }
        if (vm) lua_close(vm);
        vm = nl;
        return 0;
    }
}

/* -- the cover (F7) ------------------------------------------------------
 *
 * Not part of what a platform owes the console either. F7, while watching,
 * writes the frame on screen as the cart's cover.png (SPEC.md 3.6): the author
 * choosing the picture, so it is off for anyone merely playing. A cover is
 * 128x128, so the frame's centre square is brought to that size -- every k-th
 * pixel when its side is k * 128, else each output pixel the mean of the
 * source area it covers, weighted by overlap and rounded half up, in integers.
 * That is moycore/cover.py's square(), which `moy build` uses, and
 * test/cover_test.py holds this one to it through --dump --cover.
 *
 * Indexed when the result has 256 colours or fewer, RGB otherwise, in a stored
 * (uncompressed) deflate block: no compressor, and the largest such file --
 * RGB -- is 49,348 bytes, inside the profile's 65,536. `moy play` rewrites it
 * smaller with moycore's encoder.
 */
#define COVER 128
#define COVER_RAW (COVER * (1 + COVER * 3))

static uint32_t crc_table[256];

static uint32_t crc32_of(uint32_t crc, const uint8_t *p, size_t n)
{
    size_t i;
    if (!crc_table[1]) {
        uint32_t k, v;
        int b;
        for (k = 0; k < 256; k++) {
            v = k;
            for (b = 0; b < 8; b++) v = (v & 1u) ? 0xEDB88320u ^ (v >> 1) : v >> 1;
            crc_table[k] = v;
        }
    }
    crc = ~crc;
    for (i = 0; i < n; i++) crc = crc_table[(crc ^ p[i]) & 0xFFu] ^ (crc >> 8);
    return ~crc;
}

static uint8_t *put32(uint8_t *p, uint32_t v)
{
    p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16);
    p[2] = (uint8_t)(v >> 8);  p[3] = (uint8_t)v;
    return p + 4;
}

/* A chunk at `p` whose body is already in place after its 8-byte head. */
static uint8_t *seal_chunk(uint8_t *p, const char *tag, uint32_t n)
{
    put32(p, n);
    memcpy(p + 4, tag, 4);
    return put32(p + 8 + n, crc32_of(0, p + 4, n + 4));
}

/* The frame in `px` (0xAARRGGBB, w x h) squared to COVER x COVER R, G, B. */
static void cover_square(const uint32_t *px, int w, int h, uint8_t *out)
{
    int side = w < h ? w : h, x0 = (w - side) / 2, y0 = (h - side) / 2;
    int ox, oy, ix, iy;
    for (oy = 0; oy < COVER; oy++) {
        for (ox = 0; ox < COVER; ox++) {
            uint8_t *o = out + (oy * COVER + ox) * 3;
            if (side % COVER == 0) {
                int k = side / COVER;
                uint32_t v = px[(y0 + oy * k) * w + x0 + ox * k];
                o[0] = (uint8_t)(v >> 16); o[1] = (uint8_t)(v >> 8); o[2] = (uint8_t)v;
            } else {
                int ys = oy * side, xs = ox * side;
                uint32_t sum[3] = {0, 0, 0}, total = (uint32_t)side * (uint32_t)side;
                for (iy = ys / COVER; iy * COVER < ys + side; iy++) {
                    int top = iy * COVER > ys ? iy * COVER : ys;
                    int bot = (iy + 1) * COVER < ys + side ? (iy + 1) * COVER : ys + side;
                    for (ix = xs / COVER; ix * COVER < xs + side; ix++) {
                        int lft = ix * COVER > xs ? ix * COVER : xs;
                        int rgt = (ix + 1) * COVER < xs + side ? (ix + 1) * COVER : xs + side;
                        uint32_t wt = (uint32_t)(bot - top) * (uint32_t)(rgt - lft);
                        uint32_t v = px[(y0 + iy) * w + x0 + ix];
                        sum[0] += ((v >> 16) & 0xFFu) * wt;
                        sum[1] += ((v >> 8) & 0xFFu) * wt;
                        sum[2] += (v & 0xFFu) * wt;
                    }
                }
                o[0] = (uint8_t)((sum[0] + total / 2) / total);
                o[1] = (uint8_t)((sum[1] + total / 2) / total);
                o[2] = (uint8_t)((sum[2] + total / 2) / total);
            }
        }
    }
}

/* cover.png for the frame in `pixels` at `path`. 0, or 1 having said why. */
static int cover_write(const char *path, int w, int h)
{
    static uint8_t rgb[COVER * COVER * 3], idx[COVER * COVER], raw[COVER_RAW];
    static uint8_t png[8 + 25 + 12 + 768 + 12 + 2 + 5 + COVER_RAW + 4 + 12];
    static const uint8_t sig[8] = {0x89, 'P', 'N', 'G', '\r', '\n', 0x1A, '\n'};
    uint8_t pal[256 * 3], *p = png;
    char tmp[1100];
    uint32_t a = 1, b = 0;
    size_t i, nraw = 0, row;
    int npal = 0, side = w < h ? w : h;
    FILE *f;

    cover_square(pixels, w, h, rgb);
    for (i = 0; i < (size_t)COVER * COVER && npal >= 0; i++) {
        int j;
        for (j = 0; j < npal && memcmp(pal + j * 3, rgb + i * 3, 3); j++) {}
        if (j == npal) {
            if (npal == 256) { npal = -1; break; }
            memcpy(pal + npal * 3, rgb + i * 3, 3);
            npal++;
        }
        idx[i] = (uint8_t)j;
    }
    for (row = 0; row < COVER; row++) {
        raw[nraw++] = 0;
        if (npal > 0) {
            memcpy(raw + nraw, idx + row * COVER, COVER);
            nraw += COVER;
        } else {
            memcpy(raw + nraw, rgb + row * COVER * 3, COVER * 3);
            nraw += COVER * 3;
        }
    }
    for (i = 0; i < nraw; i++) {
        a = (a + raw[i]) % 65521u;
        b = (b + a) % 65521u;
    }

    memcpy(p, sig, 8);
    p += 8;
    put32(p + 8, COVER);
    put32(p + 12, COVER);
    p[16] = 8; p[17] = npal > 0 ? 3 : 2; p[18] = 0; p[19] = 0; p[20] = 0;
    p = seal_chunk(p, "IHDR", 13);
    if (npal > 0) {
        memcpy(p + 8, pal, (size_t)npal * 3);
        p = seal_chunk(p, "PLTE", (uint32_t)npal * 3);
    }
    {   /* zlib: header, ONE stored block (nraw < 65,536), adler-32 */
        uint8_t *q = p + 8;
        q[0] = 0x78; q[1] = 0x01; q[2] = 0x01;
        q[3] = (uint8_t)(nraw & 0xFFu); q[4] = (uint8_t)(nraw >> 8);
        q[5] = (uint8_t)(~nraw & 0xFFu); q[6] = (uint8_t)((~nraw >> 8) & 0xFFu);
        memcpy(q + 7, raw, nraw);
        put32(q + 7 + nraw, (b << 16) | a);
        p = seal_chunk(p, "IDAT", (uint32_t)(7 + nraw + 4));
    }
    p = seal_chunk(p, "IEND", 0);

    snprintf(tmp, sizeof tmp, "%s.part", path);
    f = fopen(tmp, "wb");
    if (!f || fwrite(png, 1, (size_t)(p - png), f) != (size_t)(p - png)) {
        if (f) fclose(f);
        remove(tmp);
        fprintf(stderr, "moy-play: cannot write %s\n", tmp);
        return 1;
    }
    fclose(f);
    if (rename(tmp, path) != 0) {
        remove(path);                       /* Windows will not rename over a file */
        if (rename(tmp, path) != 0) {
            remove(tmp);
            fprintf(stderr, "moy-play: cannot write %s\n", path);
            return 1;
        }
    }
    {   /* what was done, in moycore/cover.py's words */
        char crop[40] = "", step[40] = "";
        if (w != h) snprintf(crop, sizeof crop, "the centre %dx%d", side, side);
        if (side % COVER)
            snprintf(step, sizeof step, "area-averaged to %dx%d", COVER, COVER);
        else if (side > COVER)
            snprintf(step, sizeof step, "every %d%s pixel", side / COVER,
                     side / COVER == 2 ? "nd" : side / COVER == 3 ? "rd" : "th");
        if (crop[0] || step[0])
            fprintf(stderr, "moy-play: cover %s (%dx%d -> %dx%d: %s%s%s; %s, %ld bytes)\n",
                    path, w, h, COVER, COVER, crop, crop[0] && step[0] ? ", " : "", step,
                    npal > 0 ? "indexed" : "RGB", (long)(p - png));
        else
            fprintf(stderr, "moy-play: cover %s (%dx%d; %s, %ld bytes)\n", path, w, h,
                    npal > 0 ? "indexed" : "RGB", (long)(p - png));
    }
    return 0;
}

/* --dump: the ticks with no window, then the last frame the cart finished --
 * the one a player would be looking at -- written to `out`. 0 when the cart
 * ran, 1 when it failed. */
static int dump_run(const char *out, int frames, moy_canvas *canvas,
                    host_state *hs, int cw, int ch, int as_cover)
{
    static uint8_t shown[MOY_W * MOY_H * 2];
    size_t nbytes = 0;
    char err[512];
    int i, rc = 0;

    if (cart_init(err, sizeof err)) {
        fprintf(stderr, "moy-play: _init: %s\n", err);
        return 1;
    }
    for (i = 0; i < frames && hs->running; i++) {
        cart_reset_state(canvas);
        if (cart_update(1.0f / 30.0f, err, sizeof err)) {
            fprintf(stderr, "moy-play: _update: %s\n", err);
            rc = 1;
            break;
        }
        if (!hs->running) break;
        if (cart_draw(canvas, hs, err, sizeof err)) {
            fprintf(stderr, "moy-play: _draw: %s\n", err);
            rc = 1;
            break;
        }
        if (as_cover) {
            present(cw, ch);
            nbytes = 1;
            continue;
        }
#ifdef MOY_PLAY_WASM
        if (is_wasm) {
            const uint16_t *px = wasm_cart_frame(wc);
            size_t k, npx = (size_t)cw * (size_t)ch;
            for (k = 0; k < npx; k++) {
                shown[k * 2] = (uint8_t)(px[k] & 0xFFu);
                shown[k * 2 + 1] = (uint8_t)(px[k] >> 8);
            }
            nbytes = npx * 2;
            continue;
        }
#endif
        memcpy(shown, frame, (size_t)cw * (size_t)ch);
        nbytes = (size_t)cw * (size_t)ch;
    }
    if (nbytes && as_cover) {
        if (cover_write(out, cw, ch)) rc = 1;
    } else if (nbytes) {
        FILE *f = fopen(out, "wb");
        if (!f || fwrite(shown, 1, nbytes, f) != nbytes) {
            fprintf(stderr, "moy-play: cannot write %s\n", out);
            rc = 1;
        }
        if (f) fclose(f);
    }
    return rc;
}

/* moy's per-user data folder's files/<cart>, for the cart in folder `cart`. */
static void files_folder(const char *cart, char *out, size_t n)
{
    char name[256];
    const char *base, *end = cart + strlen(cart), *start;
    const char *home = getenv("HOME");
    size_t len;
    while (end > cart && (end[-1] == '/' || end[-1] == '\\')) end--;
    start = end;
    while (start > cart && start[-1] != '/' && start[-1] != '\\') start--;
    len = (size_t)(end - start);
    if (len > 4 && !strncmp(end - 4, ".moy", 4)) len -= 4;
    if (len == 0 || len >= sizeof name) {
        out[0] = 0;
        return;
    }
    memcpy(name, start, len);
    name[len] = 0;
#ifdef _WIN32
    base = getenv("LOCALAPPDATA");
    if (base) snprintf(out, n, "%s\\moy\\files\\%s", base, name);
    else snprintf(out, n, "%s\\AppData\\Local\\moy\\files\\%s",
                  getenv("USERPROFILE") ? getenv("USERPROFILE") : ".", name);
    (void)home;
#elif defined(__APPLE__)
    (void)base;
    snprintf(out, n, "%s/Library/Application Support/moy/files/%s", home ? home : ".", name);
#else
    base = getenv("XDG_DATA_HOME");
    if (base && base[0]) snprintf(out, n, "%s/moy/files/%s", base, name);
    else snprintf(out, n, "%s/.local/share/moy/files/%s", home ? home : ".", name);
#endif
}

int main(int argc, char **argv)
{
    moy_canvas canvas;
    moy_sheet sheet;
    moy_map map;
    moy_console con;
    host_state host;
    SDL_Window *win;
    SDL_Renderer *ren;
    SDL_Texture *tex;
    char path[1024], mainfile[MOY_NAME_MAX] = "main.lua", title[256] = "moy";
    char fps_s[16] = "30", canvas_s[16] = "320x240", runtime_s[16] = "lua", err[512];
    char srcname[MOY_SOURCES_MAX][MOY_NAME_MAX];
    char *manifest;
    const char *cart = NULL, *dump = NULL, *files_arg = NULL;
    int i, scale = 0, fullscreen = 0, fps, frame_ms, cw, ch, nsrc, frames = 2;
    int watch = 0, live = 1, arate = 0, as_cover = 0;
    int lw, lh;              /* the renderer's logical size, as last set */
    long pages = 0;
    uint64_t limit = (uint64_t)1024 * 1024 * 1024;
    uint64_t stamp;
    uint32_t last, checked;

    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--scale") && i + 1 < argc) scale = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--fullscreen")) fullscreen = 1;
        else if (!strcmp(argv[i], "--watch")) watch = 1;
        else if (!strcmp(argv[i], "--dump") && i + 1 < argc) dump = argv[++i];
        else if (!strcmp(argv[i], "--cover")) as_cover = 1;
        else if (!strcmp(argv[i], "--frames") && i + 1 < argc) frames = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--memory-limit") && i + 1 < argc)
            limit = (uint64_t)strtoul(argv[++i], NULL, 10) * 1024u * 1024u;
        else if (!strcmp(argv[i], "--files") && i + 1 < argc) files_arg = argv[++i];
        else if (!strcmp(argv[i], "--runtimes")) {
#ifdef MOY_PLAY_WASM
            puts("lua wasm");
#else
            puts("lua");
#endif
            return 0;
        }
        else cart = argv[i];
    }
    if (!cart) {
        fprintf(stderr, "usage: moy-play <cart.moy> [--scale N] [--fullscreen]"
                        " [--watch] [--memory-limit MIB] [--files DIR]\n"
                        "       moy-play <cart.moy> --dump <out> [--frames N] [--cover]"
                        " [--files DIR]\n"
                        "       moy-play --runtimes\n");
        return 2;
    }

    snprintf(path, sizeof path, "%s/manifest.json", cart);
    manifest = slurp(path, NULL);
    moy_manifest_str(manifest, "runtime", runtime_s, sizeof runtime_s);
    /* SPEC.md 3.1: a runtime this player lacks is refused, never guessed at. */
    is_wasm = !strcmp(runtime_s, "wasm");
    if (strcmp(runtime_s, "lua") != 0 && !is_wasm) {
        fprintf(stderr, "moy-play: this cart declares runtime \"%s\"; this player "
                        "runs lua and wasm (SPEC.md 3.1)\n", runtime_s);
        return 2;
    }
#ifndef MOY_PLAY_WASM
    if (is_wasm) {
        fprintf(stderr, "moy-play: this cart declares runtime \"wasm\", and this "
                        "player was built without it; it runs lua (SPEC.md 3.1)\n");
        return 2;
    }
#endif
    if (is_wasm) snprintf(mainfile, sizeof mainfile, "main.wasm");
    moy_manifest_str(manifest, "main", mainfile, sizeof mainfile);
    moy_manifest_str(manifest, "title", title, sizeof title);
    moy_manifest_str(manifest, "canvas", canvas_s, sizeof canvas_s);
    cart_pal_ok = moy_manifest_palette(manifest, cart_pal);
    nsrc = moy_manifest_sources(manifest, mainfile, srcname, MOY_SOURCES_MAX);
    pages = moy_manifest_uint(manifest, "memory", 0);
    if (moy_manifest_writable(manifest, writable, sizeof writable) < 0) writable[0] = 0;
    if (files_arg) snprintf(files_at, sizeof files_at, "%s", files_arg);
    else if (!dump) files_folder(cart, files_at, sizeof files_at);
    /* fps is a number, not a string, so scan it as one. SPEC.md 5: 30 or 60,
     * and anything else falls back to the guaranteed 30. */
    if (manifest) {
        const char *p = strstr(manifest, "\"fps\"");
        if (p) { p = strchr(p, ':'); if (p) snprintf(fps_s, sizeof fps_s, "%d", atoi(p + 1)); }
    }
    fps = atoi(fps_s);
    if (fps != 60) fps = 30;
    frame_ms = 1000 / fps;
    /* A compiled cart is one module: `sources` does not apply, and a
     * manifest that lists it is refused (SPEC.md 16.1). */
    if (is_wasm && manifest && strstr(manifest, "\"sources\"")) nsrc = -1;
    free(manifest);

    /* SPEC.md 4: `sources` is refused, never ignored -- a cart run without its
     * prologue fails inside the author's code, which sends the reader the
     * wrong way. */
    if (nsrc < 0) {
        fprintf(stderr, "moy-play: this cart's \"sources\" is not a load order "
                        "this player can follow (SPEC.md 4)\n");
        return 2;
    }

    /* SPEC.md 1: three canvas sizes, closed set; anything else is refused,
     * never run at the wrong dimensions. */
    if (sscanf(canvas_s, "%dx%d", &cw, &ch) != 2 ||
        !((cw == 320 && ch == 240) || (cw == 160 && ch == 120) ||
          (cw == 128 && ch == 128))) {
        fprintf(stderr, "moy-play: this player has no \"%s\" canvas (SPEC.md 3.1)\n", canvas_s);
        return 2;
    }

    moy_canvas_init(&canvas, frame, cw, ch);
    moy_sheet_init(&sheet, sheet_pix);
    moy_map_init(&map, map_cells, 20, 15);
    load_sheet(cart);
    load_map(cart, &map);
    load_flags(cart);

    {   /* the sound bank. A missing sounds.json is a silent cart; a MALFORMED
         * one is worth a line on stderr, because "my music does not play" is
         * otherwise undebuggable -- but it still only means silence. */
        char *sounds;
        snprintf(path, sizeof path, "%s/sounds.json", cart);
        sounds = slurp(path, NULL);
        if (moy_bank_parse(&bank, sounds))
            fprintf(stderr, "moy-play: %s is malformed; playing silent\n", path);
        free(sounds);
    }

    /* --dump keeps its hands off the cart folder: no save is read or written,
     * so a conformance run leaves the tree as it found it. */
    if (!dump) {
        snprintf(pmem_path, sizeof pmem_path, "%s/.pmem", cart);
        { FILE *f = fopen(pmem_path, "rb");
          if (f) { if (fread(pmem_slots, sizeof pmem_slots, 1, f) != 1) memset(pmem_slots, 0, sizeof pmem_slots); fclose(f); } }
    }

    memset(&host, 0, sizeof host);
    host.running = 1;
    host.frozen = dump != NULL;
    moy_console_init(&con, &canvas, &sheet, &map);
    con.flags = flag_bytes;
    con.host.user = &host;
    con.host.btn = h_btn;
    con.host.btnp = h_btnp;
    con.host.players = h_players;
    con.host.time_ms = h_time;
    con.host.pmem_get = h_pmem_get;
    con.host.pmem_set = h_pmem_set;
    con.host.quit = h_quit;
    /* The host side of SPEC.md 6's varying core verbs. The verbs exist with or
     * without these; supplying them is what lets this port do better than the
     * fallback -- real layer memory, a composited region, a cached backdrop. */
    con.host.layer_new = h_layer_new;
    con.host.layer_free = h_layer_free;
    con.host.view = h_view;
    con.host.background = h_background;
    {
        uint32_t seed = dump ? 0u : (uint32_t)time(NULL);
        moy_srand(&con, seed);

        if (dump) {
            int rc;
            if (cart_boot(cart, mainfile, srcname, nsrc, pages, cw, ch, &con, seed,
                          limit, err, sizeof err)) {
                fprintf(stderr, "moy-play: %s\n", err);
                return 2;
            }
            rc = dump_run(dump, frames, &canvas, &host, cw, ch, as_cover);
#ifdef MOY_PLAY_WASM
            if (wc) wasm_cart_close(wc);
#endif
            if (vm) lua_close(vm);
            return rc;
        }

        /* SDL, and with it the audio hooks, before the cart boots: a compiled
         * cart copies the host's hooks as it loads. */
        if (SDL_Init(SDL_INIT_VIDEO) != 0) { fprintf(stderr, "SDL: %s\n", SDL_GetError()); return 2; }

        /* Audio is its own subsystem and its own failure domain: a machine with
         * no output device still plays the game, silently, which is exactly what
         * SPEC.md 8.3 says a host without audio hardware is. The hooks are wired
         * only when a device actually opened -- unwired hooks are NULL and the
         * verbs no-op. */
        if (SDL_InitSubSystem(SDL_INIT_AUDIO) == 0) {
            SDL_AudioSpec want, have;
            memset(&want, 0, sizeof want);
            want.freq = 44100;
            want.format = AUDIO_S16SYS;
            want.channels = 1;
            want.samples = 512;
            want.callback = audio_cb;
            adev = SDL_OpenAudioDevice(NULL, 0, &want, &have,
                                       SDL_AUDIO_ALLOW_FREQUENCY_CHANGE);
            if (adev) {
                arate = have.freq;
                moy_audio_init(&audio, &bank, arate);
                con.host.sfx        = h_sfx;
                con.host.beep       = h_beep;
                con.host.music      = h_music;
                con.host.music_stop = h_music_stop;
                con.host.sound_stop = h_sound_stop;
                con.host.volume     = h_volume;
                SDL_PauseAudioDevice(adev, 0);
            }
        }

        if (cart_boot(cart, mainfile, srcname, nsrc, pages, cw, ch, &con, seed,
                      limit, err, sizeof err)) {
            /* SPEC.md 4.3: report it with the line number and return to where
             * the cart was launched from. Never leave it running, never
             * swallow it. A compiled cart this player cannot fit ends here
             * too, with the plain sentence wasm_cart_open wrote. */
            fprintf(stderr, "moy-play: %s\n", err);
            SDL_Quit();
            return 1;
        }
    }

    if (scale < 1) {
        /* A fixed default scales the CANVAS and not the window, which means a
         * 320x240 cart opens at a sensible size and a 128x128 one opens tiny
         * -- the smaller the console a cart asked for, the smaller its window,
         * which is backwards. Aim at about two thirds of the desktop height
         * instead, so every canvas arrives about the same size on the glass.
         * Integer, because SPEC.md 1 asks for integer scaling and this is a
         * pixel console. */
        SDL_DisplayMode dm;
        scale = 3;
        if (SDL_GetDesktopDisplayMode(0, &dm) == 0 && dm.h > 0) {
            int s = (dm.h * 2 / 3) / ch;
            scale = s < 2 ? 2 : (s > 8 ? 8 : s);
        }
    }

    win = SDL_CreateWindow(title, SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
                           cw * scale, ch * scale,
                           fullscreen ? SDL_WINDOW_FULLSCREEN_DESKTOP : 0);
    {   /* vsync only when the display reports a real refresh rate. The loop
         * paces itself with SDL_Delay regardless, so vsync is tear-avoidance,
         * not timing -- and on a degenerate display mode (headless and dummy
         * drivers report 0 Hz) SDL's SIMULATED vsync turns into a ~1s stall
         * per frame. Found running the Windows build under Wine with
         * SDL_VIDEODRIVER=dummy, where "hung" was really 1 fps. */
        SDL_DisplayMode dm;
        Uint32 rflags = SDL_RENDERER_ACCELERATED;
        if (SDL_GetCurrentDisplayMode(0, &dm) == 0 && dm.refresh_rate >= 30)
            rflags |= SDL_RENDERER_PRESENTVSYNC;
        ren = SDL_CreateRenderer(win, -1, rflags);
    }
    /* SPEC.md 1: a host whose glass does not match the canvas scales and/or
     * letterboxes, and integer scaling is recommended. SDL does both for us. */
    lw = cw; lh = ch;
    SDL_RenderSetLogicalSize(ren, lw, lh);
    SDL_RenderSetIntegerScale(ren, SDL_TRUE);
    SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY, "nearest");
    tex = SDL_CreateTexture(ren, SDL_PIXELFORMAT_ARGB8888,
                            SDL_TEXTUREACCESS_STREAMING, cw, ch);

    host.t0 = SDL_GetTicks();
    if (cart_init(err, sizeof err)) { fprintf(stderr, "moy-play: _init: %s\n", err); return 1; }
    last = checked = SDL_GetTicks();
    stamp = watch ? cart_stamp(cart, srcname, nsrc) : 0;
    if (watch)
        fprintf(stderr, "moy-play: watching %s -- save a file and it reloads\n", cart);

    while (host.running) {
        SDL_Event ev;
        uint32_t now;
        float dt;
        int b, drew = 0;

        while (SDL_PollEvent(&ev)) {
            if (ev.type == SDL_QUIT) host.running = 0;
            /* THE HOST OWNS EXIT (SPEC.md 7.3). There is no exit button in the
             * console's input model and the cart never sees this key. */
            if (ev.type == SDL_KEYDOWN && ev.key.keysym.sym == SDLK_ESCAPE) host.running = 0;
            /* the author choosing the cart's cover: the frame on screen */
            if (watch && ev.type == SDL_KEYDOWN && ev.key.keysym.sym == SDLK_F7
                && !ev.key.repeat) {
                snprintf(path, sizeof path, "%s/cover.png", cart);
                cover_write(path, cw, ch);
            }
        }
        /* hot reload: poll, and rebuild the cart when the bytes on disk stop
         * matching the ones being run. A failed reload leaves the PREVIOUS
         * cart stopped rather than closing the window -- you fix the file and
         * the next save brings it back, which is the whole point of the loop. */
        if (watch && SDL_GetTicks() - checked >= WATCH_MS) {
            uint64_t now_stamp = cart_stamp(cart, srcname, nsrc);
            checked = SDL_GetTicks();
            if (now_stamp != stamp) {
                char nmain[MOY_NAME_MAX], ntitle[256], ncanvas[16];
                char nsrcname[MOY_SOURCES_MAX][MOY_NAME_MAX];
                int ncw, nch, nnsrc;
                long npages = pages;

                stamp = now_stamp;
                memcpy(nmain, mainfile, sizeof nmain);
                memcpy(ntitle, title, sizeof ntitle);
                memcpy(nsrcname, srcname, sizeof nsrcname);
                nnsrc = nsrc;
                snprintf(ncanvas, sizeof ncanvas, "%dx%d", cw, ch);

                /* the manifest moves too -- a new title, fps, canvas, main,
                 * memory, or a different set of scripts. Not the runtime: a
                 * cart that changes language is a different cart, and runs
                 * from a fresh start. */
                snprintf(path, sizeof path, "%s/manifest.json", cart);
                manifest = slurp(path, NULL);
                if (manifest) {
                    const char *fp;
                    moy_manifest_str(manifest, "main", nmain, sizeof nmain);
                    moy_manifest_str(manifest, "title", ntitle, sizeof ntitle);
                    moy_manifest_str(manifest, "canvas", ncanvas, sizeof ncanvas);
                    nnsrc = moy_manifest_sources(manifest, nmain, nsrcname,
                                                 MOY_SOURCES_MAX);
                    if (is_wasm && strstr(manifest, "\"sources\"")) nnsrc = -1;
                    npages = moy_manifest_uint(manifest, "memory", 0);
                    if (moy_manifest_writable(manifest, writable, sizeof writable) < 0)
                        writable[0] = 0;
                    fp = strstr(manifest, "\"fps\"");
                    if (fp && (fp = strchr(fp, ':')) != NULL)
                        frame_ms = 1000 / (atoi(fp + 1) == 60 ? 60 : 30);
                    free(manifest);
                }
                if (sscanf(ncanvas, "%dx%d", &ncw, &nch) != 2 ||
                    !((ncw == 320 && nch == 240) || (ncw == 160 && nch == 120) ||
                      (ncw == 128 && nch == 128))) {
                    fprintf(stderr, "moy-play: reload: no \"%s\" canvas "
                                    "(SPEC.md 3.1); keeping %dx%d\n", ncanvas, cw, ch);
                    ncw = cw; nch = ch;
                }

                if (nnsrc < 0) {
                    fprintf(stderr, "moy-play: reload: \"sources\" is not a load "
                                    "order this player can follow (SPEC.md 4)\n");
                    live = 0;
                } else {
                    /* The assets first: a compiled cart binds to them as it
                     * loads, and a Lua cart reads them from its first line. */
                    memset(sheet_pix, 0, sizeof sheet_pix);
                    load_sheet(cart);
                    memset(map_cells, 0, sizeof map_cells);
                    moy_map_init(&map, map_cells, 20, 15);
                    load_map(cart, &map);
                    load_flags(cart);
                    if (ncw != cw || nch != ch) {
                        cw = ncw; ch = nch;
                        moy_canvas_init(&canvas, frame, cw, ch);
                        SDL_DestroyTexture(tex);
                        tex = SDL_CreateTexture(ren, SDL_PIXELFORMAT_ARGB8888,
                                                SDL_TEXTUREACCESS_STREAMING, cw, ch);
                        lw = cw; lh = ch;
                        SDL_RenderSetLogicalSize(ren, lw, lh);
                    }
                    if (cart_boot(cart, nmain, nsrcname, nnsrc, npages, cw, ch, &con,
                                  (uint32_t)time(NULL), limit, err, sizeof err)) {
                        /* the common case: a syntax error mid-edit. Say it and
                         * wait; what was running has not been torn down. */
                        fprintf(stderr, "moy-play: reload: %s\n", err);
                        live = 0;
                    } else {
                        memcpy(mainfile, nmain, sizeof mainfile);
                        memcpy(srcname, nsrcname, sizeof srcname);
                        nsrc = nnsrc;
                        pages = npages;
                        if (strcmp(title, ntitle)) {
                            memcpy(title, ntitle, sizeof title);
                            SDL_SetWindowTitle(win, title);
                        }
                        {   char *snd;
                            snprintf(path, sizeof path, "%s/sounds.json", cart);
                            snd = slurp(path, NULL);
                            if (adev) SDL_LockAudioDevice(adev);
                            if (moy_bank_parse(&bank, snd))
                                fprintf(stderr, "moy-play: reload: sounds.json is "
                                                "malformed; playing silent\n");
                            if (adev) {
                                moy_audio_init(&audio, &bank, arate);
                                SDL_UnlockAudioDevice(adev);
                            }
                            free(snd);
                        }
                        /* pmem is NOT reloaded: it is the player's save, and a
                         * reload is an edit to the game, not a new machine. */
                        memset(host.held, 0, sizeof host.held);
                        memset(host.prev, 0, sizeof host.prev);
                        host.view_w = host.view_h = 0;
                        host.has_bg = 0;
                        host.t0 = SDL_GetTicks();
                        moy_reset_state(&canvas);
                        live = !cart_init(err, sizeof err);
                        if (!live)
                            fprintf(stderr, "moy-play: reload: _init: %s\n", err);
                        else
                            fprintf(stderr, "moy-play: reloaded\n");
                        last = SDL_GetTicks();
                    }
                }
            }
        }

        host.keys = SDL_GetKeyboardState(NULL);
        for (b = 0; b < MOY_BTN_COUNT; b++) {
            host.prev[b] = host.held[b];
            host.held[b] = (uint8_t)(host.keys[KEYMAP[b][0]] || host.keys[KEYMAP[b][1]]);
        }

        now = SDL_GetTicks();
        dt = (float)(now - last) / 1000.0f;
        last = now;
        /* SPEC.md 5: dt always reflects real elapsed time, so movement written
         * as speed * dt is correct at any rate. Clamped so a stall does not
         * teleport everything across the screen on the next frame. */
        if (dt > 0.25f) dt = 0.25f;

        /* SPEC.md 4.3: a Lua error terminates the CART. Whether the window
         * goes with it is the player's business, not the spec's -- when we are
         * watching, the cart stops and the next save restarts it, because
         * closing the window on a typo is the opposite of a dev loop. A trap
         * ends a compiled cart the same way. */
        if (live) {
            cart_reset_state(&canvas);
            if (cart_update(dt, err, sizeof err)) {
                fprintf(stderr, "moy-play: _update: %s\n", err);
                live = 0;
                if (!watch) break;
            }
            if (live && host.running) {
                if (cart_draw(&canvas, &host, err, sizeof err)) {
                    fprintf(stderr, "moy-play: _draw: %s\n", err);
                    live = 0;
                    if (!watch) break;
                } else {
                    drew = 1;
                }
            }
            if (!live && watch)
                fprintf(stderr, "moy-play: cart stopped -- fix it and save\n");
        }

        /* Only a frame the cart finished is shown: one its _draw died in the
         * middle of is partial, and the window keeps the last whole one. */
        if (drew) present(cw, ch);
        SDL_UpdateTexture(tex, NULL, pixels, cw * 4);
        SDL_RenderClear(ren);
        if (host.view_w > 0 && host.view_h > 0
            && (host.view_w < cw || host.view_h < ch)) {
            /* SPEC.md 6 view: present the CENTERED region the cart declared,
             * at the largest integer scale that fits -- which is how a
             * converted 128x128 cart fills the glass instead of sitting in a
             * letterbox.
             *
             * The region becomes the renderer's LOGICAL SIZE, and SDL does the
             * scaling it is already doing for the canvas. The arithmetic that
             * used to be here built a destination rect out of
             * SDL_GetRendererOutputSize -- window pixels -- and handed it to
             * SDL_RenderCopy, whose rects are in LOGICAL units whenever a
             * logical size is set. So the destination was multiplied by the
             * canvas scale a second time and the window showed the top-left
             * corner of the game, magnified. Integer scaling is already on
             * (below), which is the property that arithmetic was for. */
            SDL_Rect src;
            src.x = (cw - host.view_w) / 2;
            src.y = (ch - host.view_h) / 2;
            src.w = host.view_w;
            src.h = host.view_h;
            if (lw != host.view_w || lh != host.view_h) {
                lw = host.view_w; lh = host.view_h;
                SDL_RenderSetLogicalSize(ren, lw, lh);
            }
            SDL_RenderCopy(ren, tex, &src, NULL);
        } else {
            if (lw != cw || lh != ch) {
                lw = cw; lh = ch;
                SDL_RenderSetLogicalSize(ren, lw, lh);
            }
            SDL_RenderCopy(ren, tex, NULL, NULL);
        }
        SDL_RenderPresent(ren);

        {   /* Hold the declared rate. vsync usually does this already; the
             * delay is what keeps a 30fps cart at 30 on a 144Hz panel. */
            int spent = (int)(SDL_GetTicks() - now);
            if (spent < frame_ms) SDL_Delay((uint32_t)(frame_ms - spent));
        }
    }

#ifdef MOY_PLAY_WASM
    if (wc) wasm_cart_close(wc);
    if (adev) pcm_report();
#endif
    if (vm) lua_close(vm);
    if (adev) SDL_CloseAudioDevice(adev);
    SDL_DestroyTexture(tex);
    SDL_DestroyRenderer(ren);
    SDL_DestroyWindow(win);
    SDL_Quit();
    return 0;
}
