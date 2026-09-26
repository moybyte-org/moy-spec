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
 *     quit.wat with a zero return and the host's quit hook called.
 *
 * Exits non-zero on the first failure.
 *
 * `play` is the same binding as a conformance player for compiled carts
 * (conformance/wasm_run.py): it runs a cart's ticks with the clock stopped
 * and writes the last frame it presented, RGB565 little-endian. Exit 0 when
 * the cart ran; 1 when it trapped, with the last whole frame written if there
 * was one; 2 when it was refused, with nothing written. A cart whose load
 * footprint -- its declared memory, its module and the interpreter's stack --
 * is over the limit (1024 MiB unless --limit says) is refused before it loads.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "moy.h"
#include "moy_wasm.h"

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

static void hello(const char *frame_out)
{
    char path[1024], err[256];
    loaded l;
    moy_wasm w;
    FILE *f;
    size_t i;
    uint8_t *bytes;
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
    };

    snprintf(cart, sizeof cart, "%s/hello.moy", dir);
    snprintf(path, sizeof path, "%s/main.wasm", cart);
    fresh_console();
    if (load(path, &l, err, sizeof err)) {
        CHECK(0, "hello: load: %s", err);
        return;
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
        return;
    }
    memset(&w, 0, sizeof w);
    w.read = h_read;
    CHECK(moy_wasm_open(&w, &con, l.env) == 0, "hello: open");
    CHECK(moy_wasm_init(&w, err, sizeof err) == 0, "hello: _init: %s", err);
    CHECK(moy_wasm_update(&w, 1.0f / 30.0f, err, sizeof err) == 0, "hello: _update: %s", err);
    moy_reset_state(&canvas);
    CHECK(moy_wasm_draw(&w, err, sizeof err) == 0, "hello: _draw: %s", err);
    for (i = 0; i < sizeof REPORTS / sizeof REPORTS[0]; i++)
        CHECK(pmem[REPORTS[i].slot] == REPORTS[i].want, "hello: %s: pmem[%d] = %d, want %d",
              REPORTS[i].what, REPORTS[i].slot, (int)pmem[REPORTS[i].slot],
              (int)REPORTS[i].want);

    bytes = (uint8_t *)malloc(sizeof screen_px);
    for (i = 0; i < MOY_W * MOY_H; i++) {
        bytes[i * 2] = (uint8_t)(screen_px[i] & 0xFFu);
        bytes[i * 2 + 1] = (uint8_t)(screen_px[i] >> 8);
    }
    f = fopen(frame_out, "wb");
    if (f) {
        fwrite(bytes, 1, sizeof screen_px, f);
        fclose(f);
    }
    printf("  hello: frame crc32 %08x -> %s\n", (unsigned)crc32(bytes, sizeof screen_px),
           frame_out);
    free(bytes);
    moy_wasm_close(&w);
    CHECK(!layer_used, "hello: close released the layer");
    unload(&l);
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
    int i, frames = 2, shown = 0;
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
        fprintf(stderr, "usage: wasm_test play <cart> <out> [--frames N] [--limit MIB]\n");
        return 2;
    }
    snprintf(cart, sizeof cart, "%s", argv[2]);
    out = argv[3];
    for (i = 4; i + 1 < argc; i++) {
        if (!strcmp(argv[i], "--frames")) frames = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--limit")) limit = (uint64_t)atoi(argv[++i]) * 1024u * 1024u;
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
    if (moy_wasm_open(&w, &con, l.env)) {
        fprintf(stderr, "wasm_test: refused: a hook is missing\n");
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
    unload(&l);
    free(frame);
    return 0;

trapped:
    fprintf(stderr, "wasm_test: the cart trapped: %s\n", err);
    if (shown) write_frame(out, frame, n * 2);
    moy_wasm_close(&w);
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
    hello(argv[2]);
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

    wasm_runtime_destroy();
    if (failures) {
        printf("wasm test: %d failure%s\n", failures, failures == 1 ? "" : "s");
        return 1;
    }
    printf("wasm test: the binding runs, refuses and traps as the proposal says\n");
    return 0;
}
