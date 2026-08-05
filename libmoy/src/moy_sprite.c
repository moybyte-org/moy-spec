/* Sprites, the sheet, the tilemap and text (SPEC.md 3.2, 3.3, 6, 7.1, 7.2).
 *
 * Split from the primitives because these are the verbs that read ASSETS, and
 * because they are where the transparency rules live -- three independent
 * sources (an image's own key, the call's colorkey, the cart's palt) that all
 * have to be consulted, since they come from three different places.
 */

#include <string.h>

#include "moy.h"

/* moy_put is file-local in moy_canvas.c on purpose -- the framebuffer should
 * have exactly one writer. These verbs need it too, so it is re-stated here
 * rather than exported: keeping it internal to the library is what stops a
 * host reaching past camera/clip/pal by accident. */
static void moy_put(moy_canvas *c, int x, int y, int ci)
{
    x -= c->cam_x;
    y -= c->cam_y;
    if (x < c->clip_x0 || x >= c->clip_x1 || y < c->clip_y0 || y >= c->clip_y1)
        return;
    c->pix[y * c->w + x] = c->pal[ci & 63];
}

/* ---------------------------------------------------------------- text -- */

void moy_print(moy_canvas *c, const uint8_t *s, size_t len, int x, int y, int col)
{
    /* One 8px cell per BYTE (SPEC.md 6). Column j left to right, bit 0 of each
     * column byte is the TOP row, and every byte advances -- including the ones
     * with no glyph, which is what keeps two implementations agreeing about
     * where the text AFTER a stray byte lands. */
    size_t k;
    int cx = x, ci = col & 63;
    for (k = 0; k < len; k++) {
        int code = s[k];
        if (code >= 0x20 && code <= 0x7F) {
            const uint8_t *g = moy_font_data + (code - 0x20) * 8;
            int j;
            for (j = 0; j < 8; j++) {
                int bits = g[j], py = y;
                while (bits) {
                    if (bits & 1) moy_put(c, cx + j, py, ci);
                    bits >>= 1;
                    py++;
                }
            }
        }
        cx += 8;
    }
}

/* --------------------------------------------------------------- sheet -- */

void moy_sheet_init(moy_sheet *s, uint8_t *pix) { s->pix = pix; }

int moy_sheet_pget(const moy_sheet *s, int x, int y)
{
    /* 0 outside the sheet, so sspr reading past the edge samples blank rather
     * than trapping. */
    if (x < 0 || x >= MOY_SHEET_W || y < 0 || y >= MOY_SHEET_H) return 0;
    return s->pix[y * MOY_SHEET_W + x];
}

void moy_spr(moy_canvas *c, const moy_sheet *s, int n, int x, int y,
             int colorkey, int scale, int flip)
{
    int ox, oy, sy, sx, fx, fy;
    if (n < 0 || n >= MOY_TILES) return;      /* a blank tile is legal, not an error */
    ox = (n % MOY_SHEET_COLS) * MOY_TILE;     /* SPEC.md 3.2 addressing */
    oy = (n / MOY_SHEET_COLS) * MOY_TILE;
    fx = flip & MOY_FLIP_X;
    fy = (flip >> 1) & 1;
    if (scale < 1) scale = 1;
    for (sy = 0; sy < MOY_TILE; sy++) {
        int ssy = fy ? (MOY_TILE - 1 - sy) : sy;
        for (sx = 0; sx < MOY_TILE; sx++) {
            int ssx = fx ? (MOY_TILE - 1 - sx) : sx;
            int p = s->pix[(oy + ssy) * MOY_SHEET_W + (ox + ssx)];
            /* Three transparency sources, checked independently because they
             * arrive from three different places: the call's colorkey, a
             * negative sentinel, and the cart's global palt. */
            if (p == colorkey || p < 0 || c->palt[p & 63]) continue;
            if (scale == 1)
                moy_put(c, x + sx, y + sy, p);
            else
                moy_rect(c, x + sx * scale, y + sy * scale, scale, scale, p);
        }
    }
}

void moy_sspr(moy_canvas *c, const moy_sheet *s, int sx, int sy, int sw, int sh,
              int dx, int dy, int dw, int dh, int colorkey, int flip)
{
    /* Addresses the sheet in PIXELS and scales arbitrarily -- that is the whole
     * difference from spr. Nearest-neighbour. PROVISIONAL (SPEC.md 6.1). */
    int i, j, fx = flip & 1, fy = (flip >> 1) & 1;
    if (sw <= 0 || sh <= 0 || dw <= 0 || dh <= 0) return;
    for (j = 0; j < dh; j++) {
        int v = (j * sh) / dh;
        int ty = dy + j;
        if (fy) v = sh - 1 - v;
        for (i = 0; i < dw; i++) {
            int u = (i * sw) / dw, p;
            if (fx) u = sw - 1 - u;
            p = moy_sheet_pget(s, sx + u, sy + v);
            if (p == colorkey || c->palt[p & 63]) continue;
            moy_put(c, dx + i, ty, p);
        }
    }
}

/* ----------------------------------------------------------------- map -- */

void moy_map_init(moy_map *m, uint8_t *cells, int w, int h)
{
    m->cells = cells;
    m->w = w;
    m->h = h;
}

int moy_mget(const moy_map *m, int x, int y)
{
    /* -1 for empty AND for out of range, deliberately collapsed (SPEC.md 7.2):
     * a cart walking off the edge of its level should see the same nothing it
     * sees in a hole, so collision code needs no bounds check of its own. */
    if (x < 0 || x >= m->w || y < 0 || y >= m->h) return -1;
    return (int)m->cells[y * m->w + x] - 1;
}

void moy_mset(moy_map *m, int x, int y, int tile)
{
    if (x < 0 || x >= m->w || y < 0 || y >= m->h) return;
    if (tile < 0) {
        m->cells[y * m->w + x] = 0;
        return;
    }
    if (tile > MOY_MAP_MAX_ID) tile = MOY_MAP_MAX_ID;
    m->cells[y * m->w + x] = (uint8_t)(tile + 1);
}

void moy_map_draw(moy_canvas *c, const moy_map *m, const moy_sheet *s,
                  int mx, int my, int w, int h, int sx, int sy,
                  int colorkey, int scale)
{
    /* Straight per-cell blit through moy_spr, so camera, clip, pal and palt all
     * apply and a map tile is pixel-identical to the same tile drawn by hand.
     * Empty cells are skipped, leaving whatever was underneath -- which is what
     * makes a tilemap composable with a background. */
    int cy, cx, step;
    if (scale < 1) scale = 1;
    step = MOY_TILE * scale;
    for (cy = 0; cy < h; cy++) {
        for (cx = 0; cx < w; cx++) {
            int tid = moy_mget(m, mx + cx, my + cy);
            if (tid < 0) continue;
            moy_spr(c, s, tid, sx + cx * step, sy + cy * step,
                    colorkey, scale, MOY_FLIP_NONE);
        }
    }
}
