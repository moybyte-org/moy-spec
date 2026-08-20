/* moy-play -- a desktop moy console in SDL2, and the porting layer as a
 * worked example.
 *
 *   moy-play <cart.moy> [--scale N] [--fullscreen] [--watch]
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

static uint8_t  frame[MOY_W * MOY_H];
static uint8_t  sheet_pix[MOY_SHEET_W * MOY_SHEET_H];
static uint8_t  map_cells[MOY_MAP_MAX * MOY_MAP_MAX];
static uint32_t pixels[MOY_W * MOY_H];          /* ARGB8888 for the texture */
static int32_t  pmem_slots[256];
static char     pmem_path[1024];

/* -- the host (SPEC.md 7.3, 9) ------------------------------------------- */

typedef struct {
    const uint8_t *keys;        /* SDL's keyboard state, refreshed per frame */
    uint8_t held[MOY_BTN_COUNT];
    uint8_t prev[MOY_BTN_COUNT];
    uint32_t t0;
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
static uint32_t h_time(void *u)    { return SDL_GetTicks() - ((host_state *)u)->t0; }
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

static void audio_cb(void *ud, Uint8 *stream, int len)
{
    (void)ud;
    moy_audio_render(&audio, (int16_t *)(void *)stream, len / 2);
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

/* A manifest field, by minimal scan. A real host wants a JSON parser -- it has
 * `extensions` and `runtime` to refuse on (SPEC.md 3.1, 10) and a possible
 * `palette` to honour (2.2). This example reads the fields it needs. */
static void manifest_str(const char *text, const char *key, char *out, size_t n)
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

static uint64_t cart_stamp(const char *dir, const char *mainfile)
{
    static const char *const also[] = {
        "manifest.json", "sprites.moygfx", "map.moymap",
        "sounds.json", "config.json"
    };
    uint64_t h = 14695981039346656037ull;
    size_t k;
    for (k = 0; k <= sizeof also / sizeof *also; k++) {
        char path[1024];
        long n = 0;
        char *t;
        snprintf(path, sizeof path, "%s/%s", dir, k ? also[k - 1] : mainfile);
        t = slurp(path, &n);
        if (t) { h = fnv1a(h, t, (size_t)n); free(t); }
        h = fnv1a(h, "|", 1);       /* a file appearing or vanishing counts */
    }
    return h;
}

int main(int argc, char **argv)
{
    moy_canvas canvas;
    moy_sheet sheet;
    moy_map map;
    moy_console con;
    host_state host;
    lua_State *L;
    SDL_Window *win;
    SDL_Renderer *ren;
    SDL_Texture *tex;
    char path[1024], mainfile[256] = "main.lua", title[256] = "moy";
    char fps_s[16] = "30", canvas_s[16] = "320x240", err[512];
    char *manifest, *source;
    const char *cart = NULL;
    int i, scale = 0, fullscreen = 0, fps, frame_ms, cw, ch;
    int watch = 0, live = 1, arate = 0;
    int lw, lh;              /* the renderer's logical size, as last set */
    uint64_t stamp;
    uint32_t last, checked;

    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--scale") && i + 1 < argc) scale = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--fullscreen")) fullscreen = 1;
        else if (!strcmp(argv[i], "--watch")) watch = 1;
        else cart = argv[i];
    }
    if (!cart) {
        fprintf(stderr, "usage: moy-play <cart.moy> [--scale N] [--fullscreen]"
                        " [--watch]\n");
        return 2;
    }

    snprintf(path, sizeof path, "%s/manifest.json", cart);
    manifest = slurp(path, NULL);
    manifest_str(manifest, "main", mainfile, sizeof mainfile);
    manifest_str(manifest, "title", title, sizeof title);
    manifest_str(manifest, "canvas", canvas_s, sizeof canvas_s);
    /* fps is a number, not a string, so scan it as one. SPEC.md 5: 30 or 60,
     * and anything else falls back to the guaranteed 30. */
    if (manifest) {
        const char *p = strstr(manifest, "\"fps\"");
        if (p) { p = strchr(p, ':'); if (p) snprintf(fps_s, sizeof fps_s, "%d", atoi(p + 1)); }
    }
    fps = atoi(fps_s);
    if (fps != 60) fps = 30;
    frame_ms = 1000 / fps;
    free(manifest);

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

    snprintf(pmem_path, sizeof pmem_path, "%s/.pmem", cart);
    { FILE *f = fopen(pmem_path, "rb");
      if (f) { if (fread(pmem_slots, sizeof pmem_slots, 1, f) != 1) memset(pmem_slots, 0, sizeof pmem_slots); fclose(f); } }

    memset(&host, 0, sizeof host);
    host.running = 1;
    moy_console_init(&con, &canvas, &sheet, &map);
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
    moy_srand(&con, (uint32_t)time(NULL));

    snprintf(path, sizeof path, "%s/%s", cart, mainfile);
    source = slurp(path, NULL);
    if (!source) { fprintf(stderr, "moy-play: cannot read %s\n", path); return 2; }

    L = luaL_newstate();
    moy_lua_open(L, &con);
    if (luaL_loadbuffer(L, source, strlen(source), mainfile) != LUA_OK ||
        lua_pcall(L, 0, 0, 0) != LUA_OK) {
        /* SPEC.md 4.3: report it with the line number and return to where the
         * cart was launched from. Never leave it running, never swallow it. */
        fprintf(stderr, "moy-play: %s\n", lua_tostring(L, -1));
        return 1;
    }
    free(source);

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
    if (moy_lua_init(L, err, sizeof err)) { fprintf(stderr, "moy-play: _init: %s\n", err); return 1; }
    last = checked = SDL_GetTicks();
    stamp = watch ? cart_stamp(cart, mainfile) : 0;
    if (watch)
        fprintf(stderr, "moy-play: watching %s -- save a file and it reloads\n", cart);

    while (host.running) {
        SDL_Event ev;
        uint32_t now;
        float dt;
        int b;

        while (SDL_PollEvent(&ev)) {
            if (ev.type == SDL_QUIT) host.running = 0;
            /* THE HOST OWNS EXIT (SPEC.md 7.3). There is no exit button in the
             * console's input model and the cart never sees this key. */
            if (ev.type == SDL_KEYDOWN && ev.key.keysym.sym == SDLK_ESCAPE) host.running = 0;
        }
        /* hot reload: poll, and rebuild the cart when the bytes on disk stop
         * matching the ones being run. A failed reload leaves the PREVIOUS
         * cart stopped rather than closing the window -- you fix the file and
         * the next save brings it back, which is the whole point of the loop. */
        if (watch && SDL_GetTicks() - checked >= WATCH_MS) {
            uint64_t now_stamp = cart_stamp(cart, mainfile);
            checked = SDL_GetTicks();
            if (now_stamp != stamp) {
                char nmain[256], ntitle[256], ncanvas[16];
                int ncw, nch;
                char *src2;

                stamp = now_stamp;
                memcpy(nmain, mainfile, sizeof nmain);
                memcpy(ntitle, title, sizeof ntitle);
                snprintf(ncanvas, sizeof ncanvas, "%dx%d", cw, ch);

                /* the manifest moves too -- a new title, fps, canvas or main */
                snprintf(path, sizeof path, "%s/manifest.json", cart);
                manifest = slurp(path, NULL);
                if (manifest) {
                    const char *fp;
                    manifest_str(manifest, "main", nmain, sizeof nmain);
                    manifest_str(manifest, "title", ntitle, sizeof ntitle);
                    manifest_str(manifest, "canvas", ncanvas, sizeof ncanvas);
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

                snprintf(path, sizeof path, "%s/%s", cart, nmain);
                src2 = slurp(path, NULL);
                if (!src2) {
                    fprintf(stderr, "moy-play: reload: cannot read %s\n", path);
                    live = 0;
                } else {
                    lua_State *nl = luaL_newstate();
                    moy_lua_open(nl, &con);
                    if (luaL_loadbuffer(nl, src2, strlen(src2), nmain) != LUA_OK ||
                        lua_pcall(nl, 0, 0, 0) != LUA_OK) {
                        /* the common case: a syntax error mid-edit. Say it and
                         * wait; nothing has been torn down yet. */
                        fprintf(stderr, "moy-play: reload: %s\n", lua_tostring(nl, -1));
                        lua_close(nl);
                        live = 0;
                    } else {
                        lua_close(L);           /* committed from here */
                        L = nl;
                        memcpy(mainfile, nmain, sizeof mainfile);
                        if (strcmp(title, ntitle)) {
                            memcpy(title, ntitle, sizeof title);
                            SDL_SetWindowTitle(win, title);
                        }
                        if (ncw != cw || nch != ch) {
                            cw = ncw; ch = nch;
                            moy_canvas_init(&canvas, frame, cw, ch);
                            SDL_DestroyTexture(tex);
                            tex = SDL_CreateTexture(ren, SDL_PIXELFORMAT_ARGB8888,
                                                    SDL_TEXTUREACCESS_STREAMING, cw, ch);
                            lw = cw; lh = ch;
                            SDL_RenderSetLogicalSize(ren, lw, lh);
                        }
                        memset(sheet_pix, 0, sizeof sheet_pix);
                        load_sheet(cart);
                        memset(map_cells, 0, sizeof map_cells);
                        moy_map_init(&map, map_cells, 20, 15);
                        load_map(cart, &map);
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
                        live = !moy_lua_init(L, err, sizeof err);
                        if (!live)
                            fprintf(stderr, "moy-play: reload: _init: %s\n", err);
                        else
                            fprintf(stderr, "moy-play: reloaded\n");
                        last = SDL_GetTicks();
                    }
                    free(src2);
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
         * closing the window on a typo is the opposite of a dev loop. */
        if (live) {
            moy_reset_state(&canvas);
            if (moy_lua_update(L, dt, err, sizeof err)) {
                fprintf(stderr, "moy-play: _update: %s\n", err);
                live = 0;
                if (!watch) break;
            }
            /* SPEC.md 6: background(x) declares a backdrop the host
             * repaints automatically each frame, so a cart that has one need not
             * cls() itself. Between _update and _draw, which is where the cart
             * would have done it. */
            if (live && host.has_bg) moy_cls(&canvas, host.bg);
            if (live && moy_lua_draw(L, err, sizeof err)) {
                fprintf(stderr, "moy-play: _draw: %s\n", err);
                live = 0;
                if (!watch) break;
            }
            if (!live && watch)
                fprintf(stderr, "moy-play: cart stopped -- fix it and save\n");
        }

        {   /* pixels out: the one place the console's colours become anyone's */
            const uint8_t *pal = moy_palette_default;
            int p;
            for (p = 0; p < cw * ch; p++) {
                const uint8_t *e = pal + (size_t)frame[p] * 3;
                pixels[p] = 0xFF000000u | ((uint32_t)e[0] << 16) | ((uint32_t)e[1] << 8) | e[2];
            }
        }
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

    lua_close(L);
    if (adev) SDL_CloseAudioDevice(adev);
    SDL_DestroyTexture(tex);
    SDL_DestroyRenderer(ren);
    SDL_DestroyWindow(win);
    SDL_Quit();
    return 0;
}
