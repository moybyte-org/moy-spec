/* The raster (SPEC.md 6, 7.1, 7.2).
 *
 * Every verb funnels through moy_put (per-pixel) or moy_rect (spans), and
 * those two apply all four pieces of draw state -- camera, clip, pal, palt --
 * so a verb added later inherits them by construction rather than by someone
 * remembering to. The two are the only places that touch c->pix.
 *
 * These are transcriptions of moy-spec's moycore/canvas.py, which is itself
 * verified byte-for-byte against the reference console. Where a choice looked
 * arbitrary it was kept anyway: `circ`'s truncating sqrt, `circb`'s midpoint
 * error term, Bresenham's tie-breaking. Those ARE the specification at the
 * pixel level, and "cleaning them up" would silently fork the raster.
 */

#include <math.h>
#include <string.h>

#include "moy.h"

/* ------------------------------------------------------------------ state */

void moy_canvas_init(moy_canvas *c, uint8_t *pix, int w, int h)
{
    c->pix = pix;
    c->w = w;
    c->h = h;
    moy_reset_state(c);
}

void moy_reset_state(moy_canvas *c)
{
    int i;
    c->cam_x = c->cam_y = 0;
    c->clip_x0 = c->clip_y0 = 0;
    c->clip_x1 = c->w;
    c->clip_y1 = c->h;
    for (i = 0; i < MOY_PALETTE; i++) {
        c->pal[i] = (uint8_t)i;
        c->palt[i] = 0;
    }
}

void moy_camera(moy_canvas *c, int x, int y) { c->cam_x = x; c->cam_y = y; }
void moy_camera_reset(moy_canvas *c)         { c->cam_x = c->cam_y = 0; }

void moy_clip(moy_canvas *c, int x, int y, int w, int h)
{
    /* Clamped to the canvas, so an oversized rect is a full screen rather than
     * a buffer overrun. Screen space: applied AFTER the camera offset, which is
     * what lets a scrolling cart pin a HUD clip while the world moves. */
    int x1 = x + w, y1 = y + h;
    c->clip_x0 = x < 0 ? 0 : x;
    c->clip_y0 = y < 0 ? 0 : y;
    c->clip_x1 = x1 > c->w ? c->w : x1;
    c->clip_y1 = y1 > c->h ? c->h : y1;
}

void moy_clip_reset(moy_canvas *c)
{
    c->clip_x0 = c->clip_y0 = 0;
    c->clip_x1 = c->w;
    c->clip_y1 = c->h;
}

void moy_pal(moy_canvas *c, int c0, int c1) { c->pal[c0 & 63] = (uint8_t)(c1 & 63); }

void moy_pal_reset(moy_canvas *c)
{
    int i;
    for (i = 0; i < MOY_PALETTE; i++) c->pal[i] = (uint8_t)i;
}

void moy_palt(moy_canvas *c, int col, int on) { c->palt[col & 63] = on ? 1 : 0; }

void moy_palt_reset(moy_canvas *c) { memset(c->palt, 0, MOY_PALETTE); }

/* ------------------------------------------------------------- primitives */

/* One camera-offset, clipped, pal-remapped pixel. Static and small enough to
 * inline; every per-pixel verb goes through it. */
static void moy_put(moy_canvas *c, int x, int y, int ci)
{
    x -= c->cam_x;
    y -= c->cam_y;
    if (x < c->clip_x0 || x >= c->clip_x1 || y < c->clip_y0 || y >= c->clip_y1)
        return;
    c->pix[y * c->w + x] = c->pal[ci & 63];
}

void moy_cls(moy_canvas *c, int col)
{
    /* Ignores camera and clip: a full-surface reset, not a rect. It DOES honour
     * pal, so a cart running a global recolour clears to the remapped colour
     * instead of punching an unremapped hole in its own effect. */
    memset(c->pix, c->pal[col & 63], (size_t)c->w * (size_t)c->h);
}

void moy_pix(moy_canvas *c, int x, int y, int col) { moy_put(c, x, y, col); }

int moy_pget(const moy_canvas *c, int x, int y)
{
    /* Camera-relative like the write side, so a cart that sets a camera and
     * probes a world coordinate gets the pixel it drew there. */
    x -= c->cam_x;
    y -= c->cam_y;
    if (x < 0 || x >= c->w || y < 0 || y >= c->h) return 0;
    return c->pix[y * c->w + x];
}

void moy_rect(moy_canvas *c, int x, int y, int w, int h, int col)
{
    /* The span path: camera-offset the corner, intersect with the clip rect,
     * write whole rows. Every span-shaped verb (circ, tri, scaled spr) routes
     * through here so they all clip identically. */
    int x0, y0, x1, y1, yy, n;
    uint8_t ci;
    x -= c->cam_x;
    y -= c->cam_y;
    x0 = x > c->clip_x0 ? x : c->clip_x0;
    y0 = y > c->clip_y0 ? y : c->clip_y0;
    x1 = (x + w) < c->clip_x1 ? (x + w) : c->clip_x1;
    y1 = (y + h) < c->clip_y1 ? (y + h) : c->clip_y1;
    if (x1 <= x0 || y1 <= y0) return;
    ci = c->pal[col & 63];
    n = x1 - x0;
    for (yy = y0; yy < y1; yy++)
        memset(c->pix + (size_t)yy * (size_t)c->w + (size_t)x0, ci, (size_t)n);
}

void moy_rectb(moy_canvas *c, int x, int y, int w, int h, int col)
{
    /* Four one-pixel rects, so the corners are written twice and the whole
     * thing clips like any other span verb. */
    moy_rect(c, x,         y,         w, 1, col);
    moy_rect(c, x,         y + h - 1, w, 1, col);
    moy_rect(c, x,         y,         1, h, col);
    moy_rect(c, x + w - 1, y,         1, h, col);
}

void moy_line(moy_canvas *c, int x0, int y0, int x1, int y1, int col)
{
    /* Bresenham, both endpoints inclusive. */
    int dx = x1 > x0 ? x1 - x0 : x0 - x1;
    int dy = y1 > y0 ? y0 - y1 : y1 - y0;   /* negative |dy|, as the classic form */
    int sx = x0 < x1 ? 1 : -1;
    int sy = y0 < y1 ? 1 : -1;
    int err = dx + dy, e2;
    int ci = col & 63;
    for (;;) {
        moy_put(c, x0, y0, ci);
        if (x0 == x1 && y0 == y1) break;
        e2 = 2 * err;
        if (e2 >= dy) { err += dy; x0 += sx; }
        if (e2 <= dx) { err += dx; y0 += sy; }
    }
}

void moy_circ(moy_canvas *c, int cx, int cy, int r, int col)
{
    /* One span per row, half-width from the circle equation TRUNCATED toward
     * zero. r < 0 draws nothing; r == 0 is a single pixel. */
    int dy;
    for (dy = -r; dy <= r; dy++) {
        int span = (int)sqrt((double)(r * r - dy * dy));
        moy_rect(c, cx - span, cy + dy, 2 * span + 1, 1, col);
    }
}

void moy_circb(moy_canvas *c, int cx, int cy, int r, int col)
{
    /* Midpoint, eight-way symmetry. NOT the boundary of circ() -- an outline
     * and a fill are different rasterizations, which is why the spec keeps them
     * as separate verbs. */
    int x = r, y = 0, err = 0;
    int ci = col & 63;
    while (x >= y) {
        moy_put(c, cx + x, cy + y, ci);
        moy_put(c, cx + y, cy + x, ci);
        moy_put(c, cx - y, cy + x, ci);
        moy_put(c, cx - x, cy + y, ci);
        moy_put(c, cx - x, cy - y, ci);
        moy_put(c, cx - y, cy - x, ci);
        moy_put(c, cx + y, cy - x, ci);
        moy_put(c, cx + x, cy - y, ci);
        y += 1;
        if (err <= 0) {
            err += 2 * y + 1;
        } else {
            x -= 1;
            err -= 2 * x + 1;
        }
    }
}

/* --------------------------------------------------- provisional (6.1) --- */

void moy_tri(moy_canvas *c, int x1, int y1, int x2, int y2, int x3, int y3, int col)
{
    int t, y, dy_long, dy_top, dy_bot;
    /* sort by y */
    if (y1 > y2) { t = x1; x1 = x2; x2 = t; t = y1; y1 = y2; y2 = t; }
    if (y1 > y3) { t = x1; x1 = x3; x3 = t; t = y1; y1 = y3; y3 = t; }
    if (y2 > y3) { t = x2; x2 = x3; x3 = t; t = y2; y2 = y3; y3 = t; }
    if (y3 == y1) {                       /* flat: one span through all three x */
        int lo = x1 < x2 ? x1 : x2, hi = x1 > x2 ? x1 : x2;
        if (x3 < lo) lo = x3;
        if (x3 > hi) hi = x3;
        moy_rect(c, lo, y1, hi - lo + 1, 1, col);
        return;
    }
    dy_long = y3 - y1;
    dy_top  = y2 - y1;
    dy_bot  = y3 - y2;
    for (y = y1; y <= y3; y++) {
        /* Floor division, not C truncation: the reference walks these edges
         * with Python's //, and for a negative numerator the two disagree by
         * one pixel -- which is a whole column of a leaning triangle. */
        int na = (x3 - x1) * (y - y1), xa, xb;
        xa = x1 + (na >= 0 ? na / dy_long : -(((-na) + dy_long - 1) / dy_long));
        if (y < y2) {
            int nb = (x2 - x1) * (y - y1);
            xb = x1 + (nb >= 0 ? nb / dy_top : -(((-nb) + dy_top - 1) / dy_top));
        } else if (dy_bot) {
            int nb = (x3 - x2) * (y - y2);
            xb = x2 + (nb >= 0 ? nb / dy_bot : -(((-nb) + dy_bot - 1) / dy_bot));
        } else {
            xb = x3;
        }
        if (xa > xb) { t = xa; xa = xb; xb = t; }
        moy_rect(c, xa, y, xb - xa + 1, 1, col);
    }
}

void moy_trib(moy_canvas *c, int x1, int y1, int x2, int y2, int x3, int y3, int col)
{
    moy_line(c, x1, y1, x2, y2, col);
    moy_line(c, x2, y2, x3, y3, col);
    moy_line(c, x3, y3, x1, y1, col);
}

/* -------------------------------------------------------------- readout -- */

void moy_palette_rgb888(const moy_canvas *c, const uint8_t *pal, uint8_t *out)
{
    size_t i, n = (size_t)c->w * (size_t)c->h;
    if (!pal) pal = moy_palette_default;
    for (i = 0; i < n; i++) {
        const uint8_t *e = pal + (size_t)c->pix[i] * 3;
        out[i * 3 + 0] = e[0];
        out[i * 3 + 1] = e[1];
        out[i * 3 + 2] = e[2];
    }
}

void moy_palette_rgb565(const moy_canvas *c, const uint8_t *pal, uint16_t *out)
{
    uint16_t tab[MOY_PALETTE];
    size_t i, n = (size_t)c->w * (size_t)c->h;
    if (!pal) pal = moy_palette_default;
    for (i = 0; i < MOY_PALETTE; i++) {
        const uint8_t *e = pal + i * 3;
        tab[i] = (uint16_t)(((e[0] & 0xF8) << 8) | ((e[1] & 0xFC) << 3) | (e[2] >> 3));
    }
    for (i = 0; i < n; i++) out[i] = tab[c->pix[i] & 63];
}

/* ------------------------------------------------------------- console --- */

void moy_console_init(moy_console *con, moy_canvas *c, moy_sheet *s, moy_map *m)
{
    memset(con, 0, sizeof *con);
    con->canvas = c;
    con->sheet = s;
    con->map = m;
    con->rng = 1;
}

void moy_srand(moy_console *con, uint32_t seed)
{
    con->rng = seed ? seed : 0x9E3779B9u;
}

float moy_rnd(moy_console *con, float n)
{
    /* xorshift32. SPEC.md 9 fixes rnd()'s RANGE and says nothing about its
     * sequence, so two conforming hosts may disagree on every number and both
     * be right -- which is exactly why no conformance scene may call it. A
     * defined generator here at least makes the question askable. */
    uint32_t x = con->rng ? con->rng : 0x9E3779B9u;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    con->rng = x;
    return (float)((double)x / 4294967296.0) * n;
}
