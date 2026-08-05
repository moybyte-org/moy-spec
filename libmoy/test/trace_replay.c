/* Replay a moy conformance trace and dump the frame.
 *
 *   trace_replay <trace.json> <out.bin> [--sheet <sprites.moygfx>]
 *                                        [--map <map.moymap>]
 *
 * moy-spec's conformance suite records each scene as a flat list of verb calls
 * (conformance/traces/) exactly so an implementation can be checked
 * before it has a Lua VM, or a cart loader, or a frame loop. This is that
 * check for libmoy: it writes 76800 bytes of palette indices, which is one of
 * the two forms conformance/run.py accepts, so
 *
 *   python3 conformance/run.py --player "…/trace_replay …/{cart} {out}"
 *
 * puts libmoy against the same golden frames as everything else.
 *
 * The JSON reader below is deliberately small and deliberately strict. It is
 * not a general parser -- it handles exactly the shapes a trace contains -- and
 * it rejects anything else rather than guessing, because a conformance harness
 * that silently skips a call it did not understand would report a pass it did
 * not earn.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "moy.h"

#define MAX_ARGS 12

typedef enum { A_INT, A_STR } argkind;

typedef struct {
    argkind kind;
    long    num;
    uint8_t str[512];        /* print text, as BYTES */
    size_t  len;
} arg;

/* ------------------------------------------------------------ json ------ */

static const char *p;        /* cursor */
static const char *pend;

static void fail(const char *what)
{
    fprintf(stderr, "trace_replay: %s (at offset %ld)\n", what, (long)(p - pend));
    exit(2);
}

static void skip_ws(void)
{
    while (p < pend && (*p == ' ' || *p == '\n' || *p == '\r' || *p == '\t')) p++;
}

static int eat(char ch)
{
    skip_ws();
    if (p < pend && *p == ch) { p++; return 1; }
    return 0;
}

static void expect(char ch)
{
    if (!eat(ch)) fail("unexpected character");
}

/* A JSON string into raw bytes. \uXXXX is accepted only for XXXX <= 0xFF: the
 * trace's own rule is that anything past ASCII travels as a LIST of byte
 * values, so a higher escape here means the trace was written by something
 * that does not share that rule, and guessing an encoding is how print starts
 * disagreeing about cell counts again. */
static void parse_string(arg *a)
{
    a->kind = A_STR;
    a->len = 0;
    expect('"');
    while (p < pend && *p != '"') {
        int ch = (unsigned char)*p++;
        if (ch == '\\') {
            if (p >= pend) fail("truncated escape");
            switch (*p++) {
            case 'n': ch = '\n'; break;
            case 't': ch = '\t'; break;
            case 'r': ch = '\r'; break;
            case 'b': ch = '\b'; break;
            case 'f': ch = '\f'; break;
            case '"': ch = '"';  break;
            case '\\': ch = '\\'; break;
            case '/': ch = '/';  break;
            case 'u': {
                char hex[5];
                long v;
                if (pend - p < 4) fail("truncated \\u escape");
                memcpy(hex, p, 4);
                hex[4] = 0;
                p += 4;
                v = strtol(hex, NULL, 16);
                if (v > 0xFF) fail("\\u escape past 0xFF: a trace carries "
                                   "non-ASCII text as a list of byte values");
                ch = (int)v;
                break;
            }
            default: fail("unknown escape");
            }
        }
        if (a->len < sizeof a->str) a->str[a->len++] = (uint8_t)ch;
    }
    expect('"');
}

/* A [1, 2, 3] byte list -- the trace's form for text past ASCII. */
static void parse_bytelist(arg *a)
{
    a->kind = A_STR;
    a->len = 0;
    expect('[');
    skip_ws();
    if (!eat(']')) {
        do {
            char *end;
            long v;
            skip_ws();
            v = strtol(p, &end, 10);
            if (end == p) fail("expected a byte value");
            p = end;
            if (v < 0 || v > 255) fail("byte value out of range");
            if (a->len < sizeof a->str) a->str[a->len++] = (uint8_t)v;
        } while (eat(','));
        expect(']');
    }
}

static int parse_arg(arg *a)
{
    skip_ws();
    if (p >= pend) return 0;
    if (*p == '"') { parse_string(a); return 1; }
    if (*p == '[') { parse_bytelist(a); return 1; }
    if (!strncmp(p, "true", 4))  { p += 4; a->kind = A_INT; a->num = 1; return 1; }
    if (!strncmp(p, "false", 5)) { p += 5; a->kind = A_INT; a->num = 0; return 1; }
    {
        char *end;
        long v = strtol(p, &end, 10);
        if (end == p) fail("expected a value");
        p = end;
        a->kind = A_INT;
        a->num = v;
        return 1;
    }
}

/* ----------------------------------------------------------- assets ----- */

static uint8_t sheet_pix[MOY_SHEET_W * MOY_SHEET_H];
static uint8_t map_cells[MOY_MAP_MAX * MOY_MAP_MAX];
static moy_sheet sheet;
static moy_map   map;

static int hexval(int ch)
{
    if (ch >= '0' && ch <= '9') return ch - '0';
    if (ch >= 'a' && ch <= 'f') return ch - 'a' + 10;
    if (ch >= 'A' && ch <= 'F') return ch - 'A' + 10;
    return -1;
}

/* sprites.moygfx: one hex nibble per pixel, up to MOY_SHEET_W per line.
 * SPEC.md 3.2 -- a short sheet leaves the rest blank, and hosts MUST accept it. */
static void load_sheet(const char *path)
{
    FILE *f = fopen(path, "rb");
    int ch, x = 0, y = 0;
    if (!f) { perror(path); exit(2); }
    while ((ch = fgetc(f)) != EOF) {
        if (ch == '\n') { if (x) { y++; x = 0; } continue; }
        if (ch == '\r') continue;
        if (y < MOY_SHEET_H && x < MOY_SHEET_W) {
            int v = hexval(ch);
            if (v < 0) { fprintf(stderr, "%s: bad hex digit\n", path); exit(2); }
            sheet_pix[y * MOY_SHEET_W + x] = (uint8_t)v;
        }
        x++;
    }
    fclose(f);
}

/* map.moymap: a `w h` header, then h rows of w*2 hex digits, each byte
 * holding tile_id + 1 (SPEC.md 3.3). */
static void load_map(const char *path)
{
    FILE *f = fopen(path, "rb");
    int w = 0, h = 0, y, x;
    if (!f) { perror(path); exit(2); }
    if (fscanf(f, "%d %d", &w, &h) != 2) { fprintf(stderr, "%s: no header\n", path); exit(2); }
    if (w < 1 || h < 1 || w > MOY_MAP_MAX || h > MOY_MAP_MAX) {
        /* Refused, not clamped: the host reserved 16 KB and a cart asking for
         * more has to be told, rather than quietly getting half a level. */
        fprintf(stderr, "%s: %dx%d is past SPEC.md 3.3's %d cap\n",
                path, w, h, MOY_MAP_MAX);
        exit(2);
    }
    for (y = 0; y < h; y++) {
        for (x = 0; x < w; x++) {
            int hi, lo;
            do { hi = fgetc(f); } while (hi == '\n' || hi == '\r' || hi == ' ');
            lo = fgetc(f);
            if (hi == EOF || lo == EOF) goto done;
            map_cells[y * w + x] = (uint8_t)((hexval(hi) << 4) | hexval(lo));
        }
    }
done:
    fclose(f);
    moy_map_init(&map, map_cells, w, h);
}

/* ----------------------------------------------------------- replay ----- */

static uint8_t frame[MOY_W * MOY_H];

int main(int argc, char **argv)
{
    moy_canvas c;
    char *blob;
    long size;
    FILE *f;
    const char *trace_path = NULL, *out_path = NULL;
    int i;

    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--sheet") && i + 1 < argc) load_sheet(argv[++i]);
        else if (!strcmp(argv[i], "--map") && i + 1 < argc) load_map(argv[++i]);
        else if (!trace_path) trace_path = argv[i];
        else out_path = argv[i];
    }
    if (!trace_path || !out_path) {
        fprintf(stderr, "usage: trace_replay <trace.json> <out.bin> "
                        "[--sheet f] [--map f]\n");
        return 2;
    }
    moy_sheet_init(&sheet, sheet_pix);
    if (!map.cells) moy_map_init(&map, map_cells, 20, 15);

    f = fopen(trace_path, "rb");
    if (!f) { perror(trace_path); return 2; }
    fseek(f, 0, SEEK_END);
    size = ftell(f);
    fseek(f, 0, SEEK_SET);
    blob = malloc((size_t)size + 1);
    if (!blob || fread(blob, 1, (size_t)size, f) != (size_t)size) {
        fprintf(stderr, "could not read %s\n", trace_path);
        return 2;
    }
    blob[size] = 0;
    fclose(f);

    moy_canvas_init(&c, frame, MOY_W, MOY_H);

    p = blob;
    pend = blob + size;
    expect('[');
    skip_ws();
    if (!eat(']')) {
        do {
            arg a[MAX_ARGS];
            char verb[32];
            int n = 0;
            size_t vlen;
            expect('[');
            parse_string(&a[0]);
            vlen = a[0].len < sizeof verb - 1 ? a[0].len : sizeof verb - 1;
            memcpy(verb, a[0].str, vlen);
            verb[vlen] = 0;
            while (eat(',')) {
                if (n >= MAX_ARGS) fail("too many arguments");
                parse_arg(&a[n++]);
            }
            expect(']');

#define N(i) ((int)a[i].num)
            if      (!strcmp(verb, "cls"))    moy_cls(&c, N(0));
            else if (!strcmp(verb, "pix"))    moy_pix(&c, N(0), N(1), N(2));
            else if (!strcmp(verb, "line"))   moy_line(&c, N(0), N(1), N(2), N(3), N(4));
            else if (!strcmp(verb, "rect"))   moy_rect(&c, N(0), N(1), N(2), N(3), N(4));
            else if (!strcmp(verb, "rectb"))  moy_rectb(&c, N(0), N(1), N(2), N(3), N(4));
            else if (!strcmp(verb, "circ"))   moy_circ(&c, N(0), N(1), N(2), N(3));
            else if (!strcmp(verb, "circb"))  moy_circb(&c, N(0), N(1), N(2), N(3));
            else if (!strcmp(verb, "tri"))    moy_tri(&c, N(0), N(1), N(2), N(3), N(4), N(5), N(6));
            else if (!strcmp(verb, "trib"))   moy_trib(&c, N(0), N(1), N(2), N(3), N(4), N(5), N(6));
            else if (!strcmp(verb, "print"))  moy_print(&c, a[0].str, a[0].len, N(1), N(2), N(3));
            else if (!strcmp(verb, "camera")) { if (n) moy_camera(&c, N(0), N(1)); else moy_camera_reset(&c); }
            else if (!strcmp(verb, "clip"))   { if (n) moy_clip(&c, N(0), N(1), N(2), N(3)); else moy_clip_reset(&c); }
            else if (!strcmp(verb, "pal"))    { if (n) moy_pal(&c, N(0), N(1)); else moy_pal_reset(&c); }
            else if (!strcmp(verb, "palt"))   { if (n) moy_palt(&c, N(0), N(1)); else moy_palt_reset(&c); }
            else if (!strcmp(verb, "spr"))    moy_spr(&c, &sheet, N(0), N(1), N(2), N(3), N(4), N(5));
            else if (!strcmp(verb, "sspr"))   moy_sspr(&c, &sheet, N(0), N(1), N(2), N(3), N(4), N(5), N(6), N(7), N(8), N(9));
            else if (!strcmp(verb, "map"))    moy_map_draw(&c, &map, &sheet, N(0), N(1), N(2), N(3), N(4), N(5), N(6), N(7));
            else if (!strcmp(verb, "tline"))  moy_tline(&c, &sheet, &map, N(0), N(1), N(2), N(3), (int32_t)N(4), (int32_t)N(5), (int32_t)N(6), (int32_t)N(7), N(8));
            else {
                /* Never skipped: an unimplemented verb is a failure to report,
                 * not a line to step over on the way to a green result. */
                fprintf(stderr, "trace_replay: unimplemented verb %s\n", verb);
                return 2;
            }
#undef N
        } while (eat(','));
        expect(']');
    }

    f = fopen(out_path, "wb");
    if (!f) { perror(out_path); return 2; }
    fwrite(frame, 1, sizeof frame, f);
    fclose(f);
    free(blob);
    return 0;
}
