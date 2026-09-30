/* make wasm-test: libmoy's wasm binding under WAMR, on Linux.
 *
 *   build/wasm_test <built fixtures dir> <frame out>
 *   build/wasm_test play <cart> <out> [--frames N] [--limit MIB]
 *
 * The fixtures are test/wasm/, assembled by tools/wat.py into the directory
 * given. This drives them the way a console would:
 *
 *   - hello.moy is checked, instantiated and run for one tick: every value
 *     _init reports through pmem is asserted, and the frame _draw leaves is
 *     written out (RGB565, little-endian) with its CRC32, for
 *     test/wasm_frame.py to hold against moycore's own rendering;
 *   - each refusal cart must fail moy_wasm_check -- except start_function,
 *     whose start function must instead trap at instantiation, since no
 *     binding exists before moy_wasm_open -- and moy_wasm_check_bytes, the
 *     check an engine without WAMR's loader runs, must refuse every one of
 *     them and pass hello;
 *   - each trap module must end with a non-zero return and a message, and
 *     quit.wat with a zero return and the host's quit hook called;
 *   - the frame hand-off: hello.moy again through a host that takes every
 *     frame, whose screen must come out the same, and handoff.wat's sequence
 *     through a host that takes none and one that takes every frame, which
 *     must leave the same screen at every step while the binding writes the
 *     taken frames only when a verb, a settle or the next hook needs them;
 *   - the sample stream: snd.wat on a host with no audio, whose queue drains
 *     by the clock at the rate, and on a host that plays it through a
 *     moy_stream, over ten simulated minutes each, counting what the cart
 *     queued against what drained; and a range outside the memory traps;
 *   - par: par.wat's items on a host with no lanes and on one with POSIX
 *     lanes (port/moy_lanes.c), which must leave the same memory, each item
 *     on its own stack and the caller's stack pointer as it was, and trap
 *     alike: the lowest trapping item's message, an import called from an
 *     item, and par's own argument checks.
 *
 * Exits non-zero on the first failure.
 *
 * `play` is the same binding as a conformance player for compiled carts
 * (conformance/wasm_run.py): it runs a cart's ticks with the clock stopped,
 * its par items on two POSIX lanes beside the calling thread (--lanes N says
 * otherwise, 0 for none), and writes the last frame it presented, RGB565
 * little-endian. Exit 0 when
 * the cart ran; 1 when it trapped, with the last whole frame written if there
 * was one; 2 when it was refused, with nothing written. A cart whose load
 * footprint -- its declared memory, its module and the interpreter's stack --
 * is over the limit (1024 MiB unless --limit says) is refused before it loads.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "moy.h"
#include "moy_audio.h"
#include "moy_wasm.h"
#include "../port/moy_lanes.h"

static char dir[512];
static int failures;

#define CHECK(cond, ...) do { if (!(cond)) { printf("  FAIL "); printf(__VA_ARGS__); \
    printf("\n"); failures++; } } while (0)

/* -- a host -------------------------------------------------------------- */

static moy_pixel screen_px[MOY_W * MOY_H];
static moy_pixel layer_px[MOY_W * MOY_H];
static int layer_used;
static uint8_t flags[MOY_FLAGS];
static int32_t pmem[256];
static int pmem_set_count;
static int quit_called;
static char cart[600];

static int h_btn(void *u, moy_button b, int player)
{ (void)u; return b == MOY_BTN_A && player == 0; }

static uint32_t h_time(void *u) { (void)u; return 1234; }

static int32_t h_pmem_get(void *u, int slot) { (void)u; return pmem[slot]; }

static void h_pmem_set(void *u, int slot, int32_t v)
{ (void)u; pmem[slot] = v; pmem_set_count++; }

static const char *h_cfg(void *u, const char *key)
{ (void)u; return strcmp(key, "speed") == 0 ? "12" : NULL; }

static moy_pixel *h_layer_new(void *u, int w, int h)
{
    (void)u;
    if (layer_used || (size_t)w * (size_t)h > sizeof layer_px / sizeof layer_px[0])
        return NULL;
    layer_used = 1;
    return layer_px;
}

static void h_layer_free(void *u, moy_pixel *p) { (void)u; (void)p; layer_used = 0; }

static void h_quit(void *u) { (void)u; quit_called = 1; }

static uint32_t h_read(void *u, const char *name, uint32_t offset, uint8_t *dst, uint32_t len)
{
    char path[1024];
    FILE *f;
    long size;
    uint32_t got = 0;
    (void)u;
    snprintf(path, sizeof path, "%s/%s", cart, name);
    f = fopen(path, "rb");
    if (!f) return 0;
    if (fgetc(f) == EOF && ferror(f)) {     /* a folder: not a file of the cart's */
        fclose(f);
        return 0;
    }
    fseek(f, 0, SEEK_END);
    size = ftell(f);
    if (size >= 0 && (uint32_t)size > offset) {
        uint32_t left = (uint32_t)size - offset;
        if (len == 0) {
            got = left;
        } else {
            fseek(f, (long)offset, SEEK_SET);
            got = (uint32_t)fread(dst, 1, len < left ? len : left, f);
        }
    }
    fclose(f);
    return got;
}

/* -- plumbing ------------------------------------------------------------ */

static uint8_t *slurp(const char *path, uint32_t *size)
{
    FILE *f = fopen(path, "rb");
    uint8_t *buf;
    long n;
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    n = ftell(f);
    fseek(f, 0, SEEK_SET);
    buf = (uint8_t *)malloc((size_t)n + 1);
    if (buf && fread(buf, 1, (size_t)n, f) != (size_t)n) {
        free(buf);
        buf = NULL;
    }
    fclose(f);
    if (buf) {
        buf[n] = 0;
        *size = (uint32_t)n;
    }
    return buf;
}

/* The manifest's "memory": the only field this needs, found by hand. */
static uint32_t manifest_pages(const char *cart_dir)
{
    char path[1024];
    uint32_t n;
    uint8_t *m;
    const char *p;
    uint32_t pages = 0;
    snprintf(path, sizeof path, "%s/manifest.json", cart_dir);
    m = slurp(path, &n);
    if (!m) return 0;
    p = strstr((const char *)m, "\"memory\"");
    if (p && (p = strchr(p, ':')) != NULL) pages = (uint32_t)strtoul(p + 1, NULL, 10);
    free(m);
    return pages;
}

static uint32_t crc32(const uint8_t *p, size_t n)
{
    uint32_t c = 0xFFFFFFFFu;
    size_t i;
    int k;
    for (i = 0; i < n; i++) {
        c ^= p[i];
        for (k = 0; k < 8; k++) c = (c >> 1) ^ (0xEDB88320u & (0u - (c & 1u)));
    }
    return ~c;
}

typedef struct {
    uint8_t *bytes;
    uint8_t *copy;               /* what moy_wasm_check reads */
    uint32_t size;
    wasm_module_t module;
    wasm_module_inst_t inst;
    wasm_exec_env_t env;
} loaded;

static int load(const char *path, loaded *l, char *err, size_t errlen)
{
    uint32_t n;
    memset(l, 0, sizeof *l);
    l->bytes = slurp(path, &n);
    l->copy = slurp(path, &l->size);
    if (!l->bytes || !l->copy) {
        snprintf(err, errlen, "cannot read %s", path);
        return -1;
    }
    /* WAMR may rewrite the buffer it loads from, so the check reads a copy. */
    l->module = wasm_runtime_load(l->bytes, n, err, (uint32_t)errlen);
    return l->module ? 0 : -1;
}

static int instantiate(loaded *l, char *err, size_t errlen)
{
    l->inst = wasm_runtime_instantiate(l->module, 64 * 1024, 0, err, (uint32_t)errlen);
    if (!l->inst) return -1;
    l->env = wasm_runtime_create_exec_env(l->inst, 64 * 1024);
    return l->env ? 0 : -1;
}

static void unload(loaded *l)
{
    if (l->env) wasm_runtime_destroy_exec_env(l->env);
    if (l->inst) wasm_runtime_deinstantiate(l->inst);
    if (l->module) wasm_runtime_unload(l->module);
    free(l->bytes);
    free(l->copy);
}

static moy_canvas canvas;
static moy_console con;

static void fresh_console(void)
{
    moy_canvas_init(&canvas, screen_px, MOY_W, MOY_H);
    moy_console_init(&con, &canvas, NULL, NULL);
    memset(flags, 0, sizeof flags);
    memset(pmem, 0, sizeof pmem);
    pmem_set_count = 0;
    quit_called = 0;
    con.flags = flags;
    con.host.btn = h_btn;
    con.host.time_ms = h_time;
    con.host.pmem_get = h_pmem_get;
    con.host.pmem_set = h_pmem_set;
    con.host.cfg = h_cfg;
    con.host.layer_new = h_layer_new;
    con.host.layer_free = h_layer_free;
    con.host.quit = h_quit;
}

/* -- the cases ----------------------------------------------------------- */

/* The frame hand-off's host half (moy_wasm.h, `frame`): it takes every frame
 * offered while `take_frames` is set, and remembers the last offer. */
static int take_frames, offers;
static const uint8_t *offered;
static const moy_pixel *offered_lut;

static int h_frame(void *u, const uint8_t *pixels, const moy_pixel *lut)
{
    (void)u;
    offers++;
    offered = pixels;
    offered_lut = lut;
    return take_frames;
}

/* One tick of hello.moy; `frame_out` NULL writes nothing. Returns the frame's
 * CRC. */
static uint32_t hello(const char *frame_out)
{
    char path[1024], err[256];
    loaded l;
    moy_wasm w;
    FILE *f;
    size_t i;
    uint8_t *bytes;
    uint32_t crc = 0;
    static const struct { int slot; int32_t want; const char *what; } REPORTS[] = {
        {0, 1, "make_layer's first handle"},
        {1, 12, "pix read back on the layer through target"},
        {2, 4, "read: the bytes of greeting.txt"},
        {3, 'm', "read: its first byte"},
        {4, 4, "read with len 0: the size"},
        {5, 0, "read: ../manifest.json stays outside"},
        {6, 0, "read: an absent name"},
        {7, 7, "camera: the previous x through out"},
        {8, 9, "camera: the previous y through out"},
        {9, 1, "btn(4): a is held"},
        {10, 0, "touch: nil as 0"},
        {11, 2, "cfg: the value's length"},
        {12, '1', "cfg: the value's first byte"},
        {13, -1, "cfg: an absent key"},
        {14, 0x81, "fget(n, -1): the byte fset wrote"},
        {15, 1, "fget(n, 7): bit 7"},
        {16, -2, "flr(-1.5)"},
        {17, 1234, "time()"},
        {18, 33, "_update's dt, in ms"},
        {19, MOY_WASM_SND_DEPTH, "snd(0, 0): the room, on a host with no audio"},
        {20, 100, "snd: a hundred frames queued"},
        {21, MOY_WASM_SND_DEPTH - 100, "snd(0, 0): the room left, the clock standing"},
    };

    snprintf(cart, sizeof cart, "%s/hello.moy", dir);
    snprintf(path, sizeof path, "%s/main.wasm", cart);
    fresh_console();
    if (load(path, &l, err, sizeof err)) {
        CHECK(0, "hello: load: %s", err);
        return 0;
    }
    CHECK(moy_wasm_check(l.module, l.copy, l.size, manifest_pages(cart), err,
                         sizeof err) == 0,
          "hello: check: %s", err);
    CHECK(moy_wasm_check_bytes(l.copy, l.size, manifest_pages(cart), err,
                               sizeof err) == 0,
          "hello: check from its bytes: %s", err);
    if (instantiate(&l, err, sizeof err)) {
        CHECK(0, "hello: instantiate: %s", err);
        unload(&l);
        return 0;
    }
    memset(&w, 0, sizeof w);
    w.read = h_read;
    w.frame = h_frame;
    CHECK(moy_wasm_open(&w, &con, l.env) == 0, "hello: open");
    CHECK(moy_wasm_init(&w, err, sizeof err) == 0, "hello: _init: %s", err);
    CHECK(moy_wasm_update(&w, 1.0f / 30.0f, err, sizeof err) == 0, "hello: _update: %s", err);
    moy_reset_state(&canvas);
    CHECK(moy_wasm_draw(&w, err, sizeof err) == 0, "hello: _draw: %s", err);
    for (i = 0; i < sizeof REPORTS / sizeof REPORTS[0]; i++)
        CHECK(pmem[REPORTS[i].slot] == REPORTS[i].want, "hello: %s: pmem[%d] = %d, want %d",
              REPORTS[i].what, REPORTS[i].slot, (int)pmem[REPORTS[i].slot],
              (int)REPORTS[i].want);

    CHECK(!moy_wasm_frame(&w, NULL), "hello: a frame is owed after the verbs over it");
    bytes = (uint8_t *)malloc(sizeof screen_px);
    for (i = 0; i < MOY_W * MOY_H; i++) {
        bytes[i * 2] = (uint8_t)(screen_px[i] & 0xFFu);
        bytes[i * 2 + 1] = (uint8_t)(screen_px[i] >> 8);
    }
    crc = crc32(bytes, sizeof screen_px);
    if (frame_out) {
        f = fopen(frame_out, "wb");
        if (f) {
            fwrite(bytes, 1, sizeof screen_px, f);
            fclose(f);
        }
        printf("  hello: frame crc32 %08x -> %s\n", (unsigned)crc, frame_out);
    }
    free(bytes);
    moy_wasm_close(&w);
    CHECK(!layer_used, "hello: close released the layer");
    unload(&l);
    return crc;
}

static void refused(const char *name)
{
    char path[1024], err[256];
    loaded l;
    snprintf(cart, sizeof cart, "%s/%s.moy", dir, name);
    snprintf(path, sizeof path, "%s/main.wasm", cart);
    err[0] = 0;
    {
        uint32_t n = 0;
        uint8_t *bytes = slurp(path, &n);
        CHECK(bytes && moy_wasm_check_bytes(bytes, n, manifest_pages(cart), err,
                                            sizeof err) != 0,
              "%s: moy_wasm_check_bytes passed it", name);
        if (bytes) printf("  ok   %s refused from its bytes: %s\n", name, err);
        free(bytes);
    }
    if (load(path, &l, err, sizeof err)) {
        printf("  ok   %s refused at load: %s\n", name, err);
        unload(&l);
        return;
    }
    err[0] = 0;
    if (!strcmp(name, "start_function")) {
        CHECK(instantiate(&l, err, sizeof err) != 0,
              "%s: a start function reaching the console should trap", name);
        printf("  ok   %s trapped at instantiation: %s\n", name, err);
    } else {
        CHECK(moy_wasm_check(l.module, l.copy, l.size, manifest_pages(cart), err,
                             sizeof err) != 0,
              "%s: moy_wasm_check passed it", name);
        printf("  ok   %s refused: %s\n", name, err);
    }
    unload(&l);
}

/* Run a module for one tick; returns what failed: 0 none, 1 _init,
 * 2 _update, 3 _draw. */
static int run(const char *name, char *err, size_t errlen)
{
    char path[1024];
    loaded l;
    moy_wasm w;
    int where = 0;
    snprintf(path, sizeof path, "%s/%s.wasm", dir, name);
    fresh_console();
    if (load(path, &l, err, errlen) || instantiate(&l, err, errlen)) {
        CHECK(0, "%s: load: %s", name, err);
        unload(&l);
        return -1;
    }
    memset(&w, 0, sizeof w);
    moy_wasm_open(&w, &con, l.env);
    if (moy_wasm_init(&w, err, errlen)) where = 1;
    else if (moy_wasm_update(&w, 1.0f / 30.0f, err, errlen)) where = 2;
    else if (!quit_called && moy_wasm_draw(&w, err, errlen)) where = 3;
    moy_wasm_close(&w);
    unload(&l);
    return where;
}

static void traps(const char *name, int want_where, const char *want_msg)
{
    char err[256] = "";
    int where = run(name, err, sizeof err);
    CHECK(where == want_where && strstr(err, want_msg),
          "%s: want a trap in hook %d saying \"%s\", got hook %d: \"%s\"",
          name, want_where, want_msg, where, err);
    if (where == want_where) printf("  ok   %s traps: %s\n", name, err);
}

/* -- the frame hand-off ------------------------------------------------------ */

static uint32_t screen_crc(void)
{
    return crc32((const uint8_t *)screen_px, sizeof screen_px);
}

static int all_sentinel(void)
{
    size_t i;
    for (i = 0; i < MOY_W * MOY_H; i++)
        if (screen_px[i] != 0xA5A5u) return 0;
    return 1;
}

/* One tick in `mode` (handoff.wat's list): 0, or 1 when a hook trapped.
 * `*after_update` is the screen between the two hooks. */
static int tick(moy_wasm *w, int mode, uint32_t *after_update, char *err, size_t errlen)
{
    moy_reset_state(&canvas);
    if (moy_wasm_update(w, (float)mode / 1000.0f, err, errlen)) return 1;
    *after_update = screen_crc();
    return moy_wasm_draw(w, err, errlen) ? 1 : 0;
}

#define HANDOFF_STEPS 14
static const int HANDOFF_MODES[HANDOFF_STEPS] = { 1, 2, 1, 3, 1, 3, 4, 5, 6, 7, 1, 3, 9, 8 };

/* handoff.wat through a host that takes no frame (`take` 0), filling ref_crc
 * and ref_pix, or through one that takes every frame and at each step does
 * what a console would -- present, settle, or nothing -- holding each screen
 * to the reference. */
static void handoff(int take, int swapped, uint32_t *ref_crc, int32_t *ref_pix)
{
    char path[1024], err[256];
    loaded l;
    moy_wasm w;
    uint8_t *kept = (uint8_t *)malloc(MOY_W * MOY_H * 2);
    int k;
    const char *who = take ? "handoff (taken)" : "handoff";
    snprintf(path, sizeof path, "%s/handoff.wasm", dir);
    fresh_console();
    for (k = 0; k < MOY_W * MOY_H; k++) screen_px[k] = 0xA5A5u;
    if (!kept || load(path, &l, err, sizeof err) || instantiate(&l, err, sizeof err)) {
        CHECK(0, "%s: load: %s", who, err);
        unload(&l);
        free(kept);
        return;
    }
    memset(&w, 0, sizeof w);
    w.wire_swapped = swapped;
    w.frame = h_frame;
    take_frames = take;
    CHECK(moy_wasm_open(&w, &con, l.env) == 0, "%s: open", who);
    CHECK(moy_wasm_init(&w, err, sizeof err) == 0, "%s: _init: %s", who, err);
    for (k = 0; k < HANDOFF_STEPS; k++) {
        int mode = HANDOFF_MODES[k], trapped, n0 = offers;
        const moy_pixel *lut = NULL;
        const uint8_t *owed;
        uint32_t mid = 0;
        pmem[0] = 0;
        trapped = tick(&w, mode, &mid, err, sizeof err);
        if (take && k == 3)                 /* step 2's owed frame, settled by _update */
            CHECK(mid == ref_crc[2], "%s: the next hook did not settle an owed frame", who);
        CHECK(trapped == (mode == 8), "%s: step %d (mode %d): %s", who, k, mode,
              trapped ? err : "no trap");
        owed = moy_wasm_frame(&w, &lut);
        if (take && mode != 3 && mode != 8)
            CHECK(offers == n0 + 1, "%s: step %d: the blit offered no frame", who, k);
        if (!take) {
            CHECK(!owed, "%s: step %d: a frame is owed with nothing taken", who, k);
            if (mode == 4 || mode == 9) {
                /* blit565 against the rule itself, pixel by pixel: the
                 * little-endian word, swapped when the screen is. */
                size_t i, bad = 0;
                for (i = 0; i < MOY_W * MOY_H; i++) {
                    uint16_t c = (uint16_t)(offered[i * 2] | (offered[i * 2 + 1] << 8));
                    uint16_t want = swapped ? (uint16_t)((c >> 8) | ((c & 0xFFu) << 8)) : c;
                    if (screen_px[i] != want) bad++;
                }
                CHECK(bad == 0, "%s: step %d (mode %d): %zu pixels differ from blit565's rule",
                      who, k, mode, bad);
            }
            ref_crc[k] = screen_crc();
            ref_pix[k] = pmem[0];
            continue;
        }
        switch (mode) {
        case 1:
            CHECK(owed == offered && lut == offered_lut && lut,
                  "%s: step %d: the owed frame is not the one offered", who, k);
            if (k == 0) {
                CHECK(all_sentinel(), "%s: a taken frame was written", who);
                moy_wasm_settle(&w);
                CHECK(!moy_wasm_frame(&w, NULL), "%s: owed after a settle", who);
            } else if (k == 4) {
                /* Shown and kept: the cart's own copy is spoiled, so the verb
                 * in step 5 can only find the frame in the host's. */
                memcpy(kept, owed, MOY_W * MOY_H);
                memset((uint8_t *)owed, 0x55, MOY_W * MOY_H);
                moy_wasm_presented(&w, kept);
                CHECK(!moy_wasm_frame(&w, NULL), "%s: owed after it was shown", who);
                continue;
            } else if (k == 10) {
                /* Shown, and the host says it wrote the screen: it did, here. */
                moy_wasm_settle(&w);
                moy_wasm_presented(&w, NULL);
            }
            /* k == 2: left owed, for the next hook to settle */
            break;
        case 4:
        case 9:
            CHECK(owed == offered && !lut, "%s: step %d: a blit565 frame owed wrongly", who, k);
            moy_wasm_settle(&w);
            break;
        case 8:
            CHECK(!owed, "%s: a trapped _draw's frame is owed", who);
            break;
        default:
            CHECK(!owed, "%s: step %d (mode %d): a frame is owed after the verbs", who,
                  k, mode);
        }
        if (k == 2) {
            CHECK(owed != NULL, "%s: step 2 owes nothing", who);
            continue;                       /* the screen is compared after step 3 */
        }
        if (mode == 8) continue;            /* a trapped frame is never compared */
        CHECK(screen_crc() == ref_crc[k], "%s: step %d (mode %d): screen %08x, want %08x",
              who, k, mode, (unsigned)screen_crc(), (unsigned)ref_crc[k]);
        CHECK(pmem[0] == ref_pix[k], "%s: step %d: pix read %d, want %d", who, k,
              (int)pmem[0], (int)ref_pix[k]);
    }
    moy_wasm_close(&w);
    CHECK(!moy_wasm_frame(&w, NULL), "%s: owed after close", who);
    unload(&l);
    free(kept);
}

static void handoffs(void)
{
    uint32_t ref_crc[HANDOFF_STEPS];
    int32_t ref_pix[HANDOFF_STEPS];
    int swapped, f0 = failures;
    for (swapped = 0; swapped < 2; swapped++) {
        handoff(0, swapped, ref_crc, ref_pix);
        handoff(1, swapped, ref_crc, ref_pix);
    }
    if (failures == f0)
        printf("  ok   taken frames reach the screen exactly when they must, both wire orders\n");
}

/* -- the sample stream ------------------------------------------------------ */

static uint32_t clock_ms;

static uint32_t h_clock_ms(void *u) { (void)u; return clock_ms; }

static moy_stream played;
static int16_t played_ring[MOY_WASM_SND_DEPTH];

/* A host with audio: the cart's frames go into a moy_stream, which the
 * harness drains the way an output would. */
static uint32_t h_snd(void *u, const uint8_t *pcm, uint32_t n)
{
    (void)u;
    return n ? moy_stream_write(&played, pcm, n) : moy_stream_room(&played);
}

/* One _update of snd.wat: offer `n` frames from `ptr` (0: the ramp). Its
 * answer, or -1 when the call trapped. */
static int32_t offer(moy_wasm *w, uint32_t n, int32_t ptr, char *err, size_t errlen)
{
    pmem[0] = (int32_t)n;
    pmem[1] = -7;
    pmem[2] = ptr;
    if (moy_wasm_update(w, 1.0f / 30.0f, err, errlen)) return -1;
    return pmem[1];
}

static int open_snd(loaded *l, moy_wasm *w, int audio, char *err, size_t errlen)
{
    char path[1024];
    snprintf(path, sizeof path, "%s/snd.wasm", dir);
    memset(w, 0, sizeof *w);
    fresh_console();
    con.host.time_ms = h_clock_ms;
    clock_ms = 0;
    if (load(path, l, err, errlen) || instantiate(l, err, errlen)) return -1;
    if (audio) {
        moy_stream_init(&played, played_ring, MOY_WASM_SND_DEPTH, MOY_WASM_SND_RATE);
        w->snd = h_snd;
    }
    if (moy_wasm_open(w, &con, l->env) || moy_wasm_init(w, err, errlen)) return -1;
    return 0;
}

/* Ten minutes of a cart that fills the room every frame, at a frame time that
 * wanders between 17 and 67 ms. On the silent host the queue drains by the
 * clock; on the playing one an output takes 256 frames whenever 256 frames of
 * clock have passed. Either way what the cart queued must be what drained plus
 * what is still queued, and what drained must be the rate times the time. */
static void stream_run(int audio)
{
    const char *who = audio ? "snd (played)" : "snd (no audio)";
    char err[256];
    loaded l;
    moy_wasm w;
    uint64_t queued = 0, drained = 0;
    uint32_t t, seed = 1;
    int16_t out[256];
    if (open_snd(&l, &w, audio, err, sizeof err)) {
        CHECK(0, "%s: open: %s", who, err);
        unload(&l);
        return;
    }
    for (t = 0; t <= 600000u;) {
        int32_t room = offer(&w, 0, 0, err, sizeof err), got;
        if (room < 0 || room > MOY_WASM_SND_DEPTH) {
            CHECK(0, "%s: at %u ms the room is %d (%s)", who, (unsigned)t, (int)room, err);
            break;
        }
        got = room ? offer(&w, (uint32_t)room, 0, err, sizeof err) : 0;
        if (got != room) {
            CHECK(0, "%s: at %u ms %d of %d frames were taken", who, (unsigned)t,
                  (int)got, (int)room);
            break;
        }
        queued += (uint32_t)got;
        seed = seed * 1103515245u + 12345u;
        t += 17u + (seed >> 16) % 51u;
        clock_ms = t;
        if (audio) {
            uint64_t due = (uint64_t)t * MOY_WASM_SND_RATE / 1000u;
            while (drained + 256u <= due) {
                memset(out, 0, sizeof out);
                moy_stream_mix(&played, out, 256, MOY_WASM_SND_RATE, 7);
                drained += 256u;
            }
        }
    }
    if (audio) {
        CHECK(played.in == queued, "%s: the stream took %u frames, the cart counted %llu",
              who, (unsigned)played.in, (unsigned long long)queued);
        CHECK(played.in == played.out + played.count,
              "%s: %u in, %u out, %u queued", who, (unsigned)played.in,
              (unsigned)played.out, (unsigned)played.count);
        CHECK(played.out == drained && played.starved == 0,
              "%s: the output took %u of %llu frames, %u starved", who,
              (unsigned)played.out, (unsigned long long)drained, (unsigned)played.starved);
    } else {
        /* The last offer filled the queue at the last clock reading before
         * the loop's end, so what drained is that reading's worth. */
        uint64_t due = (uint64_t)w.snd_ms * MOY_WASM_SND_RATE / 1000u;
        CHECK(queued == due + w.snd_level && w.snd_level == MOY_WASM_SND_DEPTH,
              "%s: queued %llu, want %llu drained and %u queued (%u)", who,
              (unsigned long long)queued, (unsigned long long)due,
              MOY_WASM_SND_DEPTH, (unsigned)w.snd_level);
    }
    printf("  ok   %s: %llu frames queued over %u s, %llu a second\n", who,
           (unsigned long long)queued, (unsigned)(t / 1000u),
           (unsigned long long)(queued * 1000u / t));
    moy_wasm_close(&w);
    unload(&l);
}

static void stream(void)
{
    char err[256];
    loaded l;
    moy_wasm w;
    int f0 = failures;
    int16_t out[64];
    int i, same;

    /* The silent host's clock, a step at a time. */
    if (open_snd(&l, &w, 0, err, sizeof err)) {
        CHECK(0, "snd: open: %s", err);
        unload(&l);
        return;
    }
    CHECK(offer(&w, 0, 0, err, sizeof err) == MOY_WASM_SND_DEPTH, "snd: an empty queue's room");
    CHECK(offer(&w, 3000, 0, err, sizeof err) == MOY_WASM_SND_DEPTH, "snd: a full queue takes the depth");
    CHECK(offer(&w, 1, 0, err, sizeof err) == 0, "snd: a full queue takes nothing");
    clock_ms = 50;
    CHECK(offer(&w, 0, 0, err, sizeof err) == 1102, "snd: 50 ms drain 1102 frames");
    clock_ms = 51;
    CHECK(offer(&w, 0, 0, err, sizeof err) == 1124, "snd: the fraction carries into the next ms");
    clock_ms = 5000;
    CHECK(offer(&w, 0, 0, err, sizeof err) == MOY_WASM_SND_DEPTH, "snd: a long wait empties the queue");
    CHECK(offer(&w, 0, 70000, err, sizeof err) == MOY_WASM_SND_DEPTH, "snd: a query reads no pointer");
    CHECK(offer(&w, 8, 65530, err, sizeof err) == -1 && strstr(err, "out of bounds"),
          "snd: frames past the memory trap (%s)", err);
    moy_wasm_close(&w);
    unload(&l);
    if (open_snd(&l, &w, 0, err, sizeof err) == 0)
        CHECK(offer(&w, 0xFFFFFFFFu, 0, err, sizeof err) == -1,
              "snd: a negative count traps");
    moy_wasm_close(&w);
    unload(&l);

    /* The playing host: the frames arrive as the cart wrote them. */
    if (open_snd(&l, &w, 1, err, sizeof err)) {
        CHECK(0, "snd (played): open: %s", err);
        unload(&l);
        return;
    }
    CHECK(offer(&w, 0, 0, err, sizeof err) == MOY_WASM_SND_DEPTH, "snd (played): the room");
    CHECK(offer(&w, 64, 0, err, sizeof err) == 64, "snd (played): 64 frames");
    CHECK(offer(&w, 0, 0, err, sizeof err) == MOY_WASM_SND_DEPTH - 64, "snd (played): the room left");
    memset(out, 0, sizeof out);
    moy_stream_mix(&played, out, 64, MOY_WASM_SND_RATE, 7);
    for (i = 0, same = 1; i < 64; i++) same &= out[i] == i * 8;
    CHECK(same, "snd (played): the output does not hold the cart's frames");
    moy_wasm_close(&w);
    unload(&l);

    stream_run(0);
    stream_run(1);
    if (failures == f0)
        printf("  ok   snd answers the room, queues to the depth, drains at the rate, traps outside memory\n");
}

/* -- play: the conformance player ------------------------------------------ */

#define PLAY_STACK (256 * 1024)

static moy_pixel play_px[MOY_W * MOY_H];
static uint8_t play_sheet[MOY_SHEET_W * MOY_SHEET_H];
static uint8_t play_cells[MOY_MAP_MAX * MOY_MAP_MAX];

static uint32_t h_clock(void *u) { (void)u; return 0; }

static moy_pixel *h_layer_alloc(void *u, int w, int h)
{
    (void)u;
    return (moy_pixel *)calloc((size_t)w * (size_t)h, sizeof(moy_pixel));
}

/* -- par --------------------------------------------------------------- */

#define PAR_ITEMS 8

/* One _update of par.wat with `n` items in `mode`, on `lanes` (NULL: none).
 * Returns 0 when it returned, 1 when it trapped (the message in err), and
 * fills `mem` with the 256 KiB of memory the update left. */
static int par_run(moy_lanes *lanes, int32_t n, int32_t mode, uint8_t *mem,
                   int32_t *sp_after, char *err, size_t errlen)
{
    char path[1024];
    loaded l;
    moy_wasm w;
    int rc;
    snprintf(path, sizeof path, "%s/par.wasm", dir);
    fresh_console();
    pmem[0] = n;
    pmem[1] = mode;
    pmem[2] = 64;
    if (load(path, &l, err, errlen) || instantiate(&l, err, errlen)) {
        CHECK(0, "par: load: %s", err);
        unload(&l);
        return -1;
    }
    CHECK(moy_wasm_check(l.module, l.copy, l.size, 4, err, errlen) == 0,
          "par: check: %s", err);
    memset(&w, 0, sizeof w);
    moy_lanes_bind(lanes, &w);
    moy_wasm_open(&w, &con, l.env);
    rc = moy_wasm_init(&w, err, errlen)
         || moy_wasm_update(&w, 1.0f / 30.0f, err, errlen);
    memcpy(mem, wasm_runtime_addr_app_to_native(l.inst, 0), 4 * 65536);
    *sp_after = pmem[3];
    moy_wasm_close(&w);
    unload(&l);
    return rc;
}

static void par_items(void)
{
    static uint8_t alone[4 * 65536], shared[4 * 65536];
    char err[256];
    int32_t sp1 = 0, sp2 = 0;
    int i, j, rc;
    moy_lanes *lanes = moy_lanes_open(2);
    static const struct { int32_t mode; const char *msg; } TRAPS[] = {
        {1, "out of bounds memory access"},
        {2, "an import called from a par item"},
        {3, "par's count is negative"},
        {4, "not 16-byte aligned"},
        {5, "out of bounds memory access"},
    };
    size_t t;

    CHECK(lanes != NULL, "par: no POSIX lanes");
    rc = par_run(NULL, PAR_ITEMS, 0, alone, &sp1, err, sizeof err);
    CHECK(rc == 0, "par: in order: %s", err);
    for (i = 0; i < PAR_ITEMS; i++) {
        uint32_t sum = 0, got, sp;
        for (j = 0; j < 8192; j++) {
            uint8_t v = (uint8_t)((i * 31 + j) & 255);
            sum += v;
            if (alone[131072 + i * 8192 + j] != v) {
                CHECK(0, "par: item %d's fill at %d", i, j);
                break;
            }
        }
        memcpy(&got, alone + 128 + i * 4, 4);
        memcpy(&sp, alone + 256 + i * 4, 4);
        CHECK(got == sum + 1, "par: item %d reported %u, want %u", i, got, sum + 1);
        CHECK(sp == 65536u + (uint32_t)(i + 1) * 4096u,
              "par: item %d ran with its stack pointer at %u", i, sp);
    }
    CHECK(sp1 == 1024, "par: the caller's stack pointer came back as %d", (int)sp1);
    printf("  ok   %d items in order: each ran once, on its own stack\n", PAR_ITEMS);

    rc = par_run(lanes, PAR_ITEMS, 0, shared, &sp2, err, sizeof err);
    CHECK(rc == 0, "par: on lanes: %s", err);
    CHECK(!memcmp(alone, shared, sizeof alone) && sp2 == sp1,
          "par: the lanes left other memory than the items in order");
    CHECK(moy_lanes_started(lanes) > 0, "par: no lane ever started an item");
    printf("  ok   the same %d items on two lanes and the caller: the same memory "
           "(lanes started %ld times)\n", PAR_ITEMS, moy_lanes_started(lanes));

    rc = par_run(lanes, 0, 0, shared, &sp2, err, sizeof err);
    CHECK(rc == 0 && sp2 == 1024, "par: no items: %s", err);

    for (t = 0; t < sizeof TRAPS / sizeof TRAPS[0]; t++) {
        char e1[256] = "", e2[256] = "";
        int r1 = par_run(NULL, PAR_ITEMS, TRAPS[t].mode, alone, &sp1, e1, sizeof e1);
        int r2 = par_run(lanes, PAR_ITEMS, TRAPS[t].mode, shared, &sp2, e2, sizeof e2);
        CHECK(r1 == 1 && r2 == 1 && strstr(e1, TRAPS[t].msg) && strstr(e2, TRAPS[t].msg),
              "par mode %d: want a trap saying \"%s\", got \"%s\" in order and \"%s\" on lanes",
              (int)TRAPS[t].mode, TRAPS[t].msg, e1, e2);
        if (r1 == 1 && r2 == 1) printf("  ok   par mode %d traps alike: %s\n", (int)TRAPS[t].mode, e2);
    }
    moy_lanes_close(lanes);
}

static void h_layer_release(void *u, moy_pixel *p) { (void)u; free(p); }

static int write_frame(const char *out, const uint8_t *frame, size_t n)
{
    FILE *f = fopen(out, "wb");
    if (!f) return 0;
    fwrite(frame, 1, n, f);
    fclose(f);
    return 1;
}

static int play(int argc, char **argv)
{
    char path[1024], err[256];
    const char *out;
    int i, frames = 2, shown = 0, n_lanes = 2;
    moy_lanes *lanes;
    uint32_t pages;
    uint64_t limit = 1024u * 1024u * 1024u, footprint;
    uint8_t *frame;
    moy_canvas cv;
    moy_sheet sheet;
    moy_map map;
    loaded l;
    moy_wasm w;
    size_t n;

    if (argc < 4) {
        fprintf(stderr, "usage: wasm_test play <cart> <out> [--frames N] [--limit MIB] "
                        "[--lanes N]\n");
        return 2;
    }
    snprintf(cart, sizeof cart, "%s", argv[2]);
    out = argv[3];
    for (i = 4; i + 1 < argc; i++) {
        if (!strcmp(argv[i], "--frames")) frames = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--limit")) limit = (uint64_t)atoi(argv[++i]) * 1024u * 1024u;
        else if (!strcmp(argv[i], "--lanes")) n_lanes = atoi(argv[++i]);
    }

    snprintf(path, sizeof path, "%s/main.wasm", cart);
    pages = manifest_pages(cart);
    {
        FILE *f = fopen(path, "rb");
        long size = -1;
        if (f) {
            fseek(f, 0, SEEK_END);
            size = ftell(f);
            fclose(f);
        }
        if (size < 0) {
            fprintf(stderr, "wasm_test: no module at %s\n", path);
            return 2;
        }
        footprint = (uint64_t)pages * 65536u + (uint64_t)size + PLAY_STACK;
    }
    if (footprint > limit) {
        fprintf(stderr, "wasm_test: this cart needs %llu KiB to load and this "
                "player gives a cart %llu KiB\n",
                (unsigned long long)(footprint / 1024u), (unsigned long long)(limit / 1024u));
        return 2;
    }

    moy_canvas_init(&cv, play_px, MOY_W, MOY_H);
    moy_sheet_init(&sheet, play_sheet);
    moy_map_init(&map, play_cells, 20, 15);
    moy_console_init(&con, &cv, &sheet, &map);
    memset(flags, 0, sizeof flags);
    memset(pmem, 0, sizeof pmem);
    con.flags = flags;
    con.host.time_ms = h_clock;
    con.host.pmem_get = h_pmem_get;
    con.host.pmem_set = h_pmem_set;
    con.host.layer_new = h_layer_alloc;
    con.host.layer_free = h_layer_release;
    con.host.quit = h_quit;
    moy_srand(&con, 0);

    if (load(path, &l, err, sizeof err)
        || moy_wasm_check(l.module, l.copy, l.size, pages, err, sizeof err)
        || instantiate(&l, err, sizeof err)) {
        fprintf(stderr, "wasm_test: refused: %s\n", err);
        unload(&l);
        return 2;
    }
    memset(&w, 0, sizeof w);
    w.read = h_read;
    lanes = moy_lanes_open(n_lanes);
    moy_lanes_bind(lanes, &w);
    w.lane_stack = PLAY_STACK;
    if (moy_wasm_open(&w, &con, l.env)) {
        fprintf(stderr, "wasm_test: refused: a hook is missing\n");
        moy_lanes_close(lanes);
        unload(&l);
        return 2;
    }

    n = (size_t)MOY_W * MOY_H;
    frame = (uint8_t *)malloc(n * 2);
    if (moy_wasm_init(&w, err, sizeof err)) goto trapped;
    for (i = 0; i < frames && !w.quitting; i++) {
        size_t k;
        moy_reset_state(&cv);
        if (moy_wasm_update(&w, 1.0f / 30.0f, err, sizeof err)) goto trapped;
        if (w.quitting) break;
        if (moy_wasm_draw(&w, err, sizeof err)) goto trapped;
        for (k = 0; k < n; k++) {
            frame[k * 2] = (uint8_t)(play_px[k] & 0xFFu);
            frame[k * 2 + 1] = (uint8_t)(play_px[k] >> 8);
        }
        shown = 1;
    }
    if (shown) write_frame(out, frame, n * 2);
    moy_wasm_close(&w);
    moy_lanes_close(lanes);
    unload(&l);
    free(frame);
    return 0;

trapped:
    fprintf(stderr, "wasm_test: the cart trapped: %s\n", err);
    if (shown) write_frame(out, frame, n * 2);
    moy_wasm_close(&w);
    moy_lanes_close(lanes);
    unload(&l);
    free(frame);
    return 1;
}

static NativeSymbol *natives;   /* WAMR sorts it in place and keeps it */

int main(int argc, char **argv)
{
    static const char *const REFUSED[] = {
        "foreign_import", "memory_mismatch", "missing_export", "bad_signature",
        "start_function"
    };
    char err[256] = "";
    size_t i;
    uint32_t crc;
    int playing = argc >= 2 && !strcmp(argv[1], "play");

    if (argc != 3 && !playing) {
        fprintf(stderr, "usage: wasm_test <built fixtures dir> <frame out>\n"
                        "       wasm_test play <cart> <out> [--frames N] [--limit MIB]\n");
        return 2;
    }
    if (!playing) snprintf(dir, sizeof dir, "%s", argv[1]);
    if (!wasm_runtime_init()) {
        fprintf(stderr, "wasm_test: WAMR did not initialise\n");
        return 1;
    }
    wasm_runtime_set_log_level(WASM_LOG_LEVEL_FATAL);
    uint32_t rows;
    moy_wasm_natives(&rows);
    natives = calloc(rows, sizeof *natives);
    if (!natives || moy_wasm_register(natives)) {
        fprintf(stderr, "wasm_test: the import table did not register\n");
        return 1;
    }
    if (playing) {
        int r = play(argc, argv);
        wasm_runtime_destroy();
        return r;
    }

    printf("wasm test: the conforming cart, one tick\n");
    crc = hello(argv[2]);
    printf("wasm test: the refusal carts\n");
    for (i = 0; i < sizeof REFUSED / sizeof REFUSED[0]; i++) refused(REFUSED[i]);
    printf("wasm test: traps and quit\n");
    traps("trap_outside_draw", 2, "blit outside _draw");
    traps("trap_bounds", 3, "out of bounds");
    traps("trap_blit_twice", 3, "second blit");
    traps("trap_handle", 1, "not a layer handle");
    CHECK(run("quit", err, sizeof err) == 0 && quit_called,
          "quit: want a clean ending with the host's quit hook called (%s)", err);
    if (quit_called) printf("  ok   quit ends the cart cleanly\n");
    printf("wasm test: the frame hand-off\n");
    take_frames = 1;
    CHECK(hello(NULL) == crc && offers > 0,
          "hello: a host taking its frame drew another screen");
    take_frames = 0;
    handoffs();
    printf("wasm test: the sample stream\n");
    stream();
    printf("wasm test: par\n");
    par_items();

    wasm_runtime_destroy();
    if (failures) {
        printf("wasm test: %d failure%s\n", failures, failures == 1 ? "" : "s");
        return 1;
    }
    printf("wasm test: the binding runs, refuses and traps as SPEC.md 16 says\n");
    return 0;
}
