/* Minimal manifest scanning, shared by the three loaders in this repository:
 * the SDL2 player, the WebAssembly player and test/run_cart.
 *
 * A deliberate shortcut rather than a JSON parser -- a real host has one
 * already, and needs it for `extensions`, `runtime` and `palette` (SPEC.md
 * 3.1, 2.2, 10). An implementer porting libmoy replaces this file with their
 * own reader; nothing below is part of what a platform owes the console.
 *
 * It exists as a FILE because of `sources`. The string scan was written out
 * three times and stayed identical by luck; a load ORDER written out three
 * times is three chances to run a cart's prologue after the code that needs
 * it, and that failure looks like a bug in the author's Lua.
 */
#ifndef MOY_MANIFEST_H
#define MOY_MANIFEST_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MOY_SOURCES_MAX 24      /* SPEC.md 4 sets no ceiling; a cart past this
                                 * is not one these example loaders read. 24
                                 * clears the worst real cart: PICO-8 allows a
                                 * cart SIXTEEN tabs and the porter makes each
                                 * one a source, which is 17 with the generated
                                 * p8.lua and 18 once a host appends a wrapper
                                 * of its own. */
#define MOY_NAME_MAX    64

/* A manifest string field. `out` is left ALONE when the key is absent, so the
 * caller seeds it with the default and reads the answer either way. */
static inline void moy_manifest_str(const char *text, const char *key,
                                    char *out, size_t n)
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

/* A manifest number field, as a non-negative whole number: `dflt` when the key
 * is absent or its value is not one. */
static inline long moy_manifest_uint(const char *text, const char *key, long dflt)
{
    char pat[64];
    const char *p;
    char *end;
    long v;
    snprintf(pat, sizeof pat, "\"%s\"", key);
    p = text ? strstr(text, pat) : NULL;
    if (!p || (p = strchr(p + strlen(pat), ':')) == NULL) return dflt;
    p++;
    while (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r') p++;
    if (*p < '0' || *p > '9') return dflt;
    v = strtol(p, &end, 10);
    return (*end == '.' || *end == 'e' || *end == 'E' || v < 0) ? dflt : v;
}

/* The manifest's `palette` (SPEC.md 2.2/3.1): 64 RGB hex strings replacing the
 * default table. Fills `out` as 64 RGB triples and returns 1, or leaves it and
 * returns 0 when the cart ships none.
 *
 * The three loaders here resolve an index to a colour themselves, so without
 * this a cart that ships a palette is drawn in MOY64 -- and every PICO-8 port
 * ships one, which made `moy play` show a converted cart in colours its author
 * never chose (green as pink, on `loop`).
 */
static inline int moy_manifest_palette(const char *text, unsigned char *out)
{
    const char *p = text ? strstr(text, "\"palette\"") : NULL;
    const char *close;
    int n = 0;
    if (!p) return 0;
    p = strchr(p, '[');
    if (!p) return 0;
    close = strchr(p, ']');
    if (!close) return 0;
    while (n < 64) {
        const char *s, *e;
        int i;
        p = strchr(p + 1, '"');
        if (!p || p > close) break;               /* past the array */
        s = p + 1;
        e = strchr(s, '"');
        if (!e || e - s != 6) return 0;           /* not "RRGGBB": refuse */
        for (i = 0; i < 3; i++) {
            char b[3];
            b[0] = s[i * 2]; b[1] = s[i * 2 + 1]; b[2] = 0;
            out[n * 3 + i] = (unsigned char)strtol(b, NULL, 16);
        }
        n++;
        p = e;
    }
    return n == 64;
}

/* The manifest's `sources` (SPEC.md 4): every script the host loads, in the
 * order it loads them. Fills `out` and returns the count, or -1 to refuse.
 *
 * ABSENT IS NOT EMPTY. No `sources` means a one-file cart, so the answer is
 * [main] -- which is why `mainfile` is an argument rather than something the
 * caller bolts on afterwards.
 *
 * -1 means the field is there and unusable: not an array, a name too long,
 * the same file twice, more files than this reads, or no `mainfile` among
 * them. SPEC.md 4 refuses such a cart, and refusing is the point -- loading
 * what parsed and skipping the rest reports the missing prologue as a fault
 * in the author's code.
 */
static inline int moy_manifest_sources(const char *text, const char *mainfile,
                                       char out[][MOY_NAME_MAX], int max)
{
    static const char KEY[] = "\"sources\"";
    const char *p = text ? strstr(text, KEY) : NULL;
    const char *end;
    int n = 0, saw_main = 0;

    if (!p) {
        if (max < 1) return -1;
        snprintf(out[0], MOY_NAME_MAX, "%s", mainfile);
        return 1;
    }
    /* Only whitespace and the colon may sit between the key and its array --
     * `strchr(p, '[')` alone would happily find a LATER field's array and
     * load a manifest's `input` list as scripts. */
    p += sizeof KEY - 1;
    while (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r') p++;
    if (*p++ != ':') return -1;
    while (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r') p++;
    if (*p != '[') return -1;
    end = strchr(p, ']');
    if (!end) return -1;

    for (p++; p < end; p++) {
        const char *s, *e;
        int i;
        if (*p != '"') continue;
        s = p + 1;
        e = strchr(s, '"');
        if (!e || e > end) return -1;
        if (n >= max || (size_t)(e - s) >= MOY_NAME_MAX) return -1;
        memcpy(out[n], s, (size_t)(e - s));
        out[n][e - s] = 0;
        for (i = 0; i < n; i++)
            if (!strcmp(out[i], out[n])) return -1;   /* each script runs once */
        if (!strcmp(out[n], mainfile)) saw_main = 1;
        n++;
        p = e;
    }
    if (!n || !saw_main) return -1;
    return n;
}

#endif /* MOY_MANIFEST_H */
