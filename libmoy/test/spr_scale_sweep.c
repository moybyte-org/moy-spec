/* Exhaustive A/B of moy_spr's scale>1 path against the moy_rect form it
 * replaced. The conformance scenes pin scale 3 with all four flips, but only
 * UNCLIPPED and at the origin -- and the whole risk of the rewrite is the
 * clipped left/top edge, where the destination loop has to start mid-source-
 * pixel (tx0/carry0). So sweep it: every scale 2..5, every flip, every colorkey
 * that matters, against every edge of the clip rect and past every corner,
 * with a camera offset on and off. Any single differing byte fails.
 *
 * The reference here is the ORIGINAL kernel, transcribed verbatim, so this is a
 * true A/B rather than a second guess at what the answer should be. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "moy.h"

#define W 320
#define H 240

static moy_pixel bufA[W * H];
static moy_pixel bufB[W * H];
static uint8_t sheet_pix[MOY_SHEET_W * MOY_SHEET_H];

/* The pre-rewrite scale>1 path, verbatim. */
static void spr_reference(moy_canvas *c, const moy_sheet *s, int n, int x, int y,
                          int colorkey, int scale, int flip)
{
    int ox, oy, sy, sx, fx, fy;
    if (n < 0 || n >= MOY_TILES) return;
    ox = (n % MOY_SHEET_COLS) * MOY_TILE;
    oy = (n / MOY_SHEET_COLS) * MOY_TILE;
    fx = flip & MOY_FLIP_X;
    fy = (flip >> 1) & 1;
    if (scale < 1) scale = 1;
    for (sy = 0; sy < MOY_TILE; sy++) {
        int ssy = fy ? (MOY_TILE - 1 - sy) : sy;
        for (sx = 0; sx < MOY_TILE; sx++) {
            int ssx = fx ? (MOY_TILE - 1 - sx) : sx;
            int p = s->pix[(oy + ssy) * MOY_SHEET_W + (ox + ssx)];
            if (p == colorkey || p < 0 || c->palt[p & 63]) continue;
            moy_rect(c, x + sx * scale, y + sy * scale, scale, scale, p);
        }
    }
}

static void reset(moy_canvas *c, moy_pixel *buf, int camx, int camy,
                  int cx, int cy, int cw, int ch, int palt_on)
{
    memset(buf, 0x5a, sizeof(bufA));
    moy_canvas_init(c, buf, W, H);
    moy_camera(c, camx, camy);
    moy_clip(c, cx, cy, cw, ch);
    if (palt_on) {
        moy_palt(c, 3, 1);          /* an extra transparent index, like a cart */
    }
}

int main(void)
{
    moy_canvas ca, cb;
    moy_sheet sh;
    int i, fails = 0, cases = 0;
    static const int CLIPS[][4] = {
        {0, 0, W, H},               /* no clip */
        {40, 30, 100, 80},          /* a window every edge can cross */
        {0, 0, 12, 9},              /* tiny, top-left */
        {300, 220, 20, 20},         /* tiny, bottom-right */
    };
    static const int CAMS[][2] = {{0, 0}, {7, -5}, {-13, 11}};
    static const int KEYS[] = {-1, 0, 3, 7};

    for (i = 0; i < MOY_SHEET_W * MOY_SHEET_H; i++) {
        sheet_pix[i] = (uint8_t)(i * 7 + (i / MOY_SHEET_W) * 3);   /* all 64 idx */
    }
    moy_sheet_init(&sh, sheet_pix);

    for (size_t ci = 0; ci < sizeof(CLIPS) / sizeof(CLIPS[0]); ci++) {
        for (size_t mi = 0; mi < sizeof(CAMS) / sizeof(CAMS[0]); mi++) {
            for (int palt_on = 0; palt_on < 2; palt_on++) {
                for (size_t ki = 0; ki < sizeof(KEYS) / sizeof(KEYS[0]); ki++) {
                    for (int scale = 2; scale <= 5; scale++) {
                        for (int flip = 0; flip < 4; flip++) {
                            /* positions: well inside, and straddling every edge
                             * and corner of the clip window by every offset a
                             * source pixel can be cut at */
                            for (int dx = -2 * scale - 3; dx <= 2 * scale + 3; dx++) {
                                for (int dy = -2 * scale - 3; dy <= 2 * scale + 3; dy++) {
                                    int x = CLIPS[ci][0] + dx;
                                    int y = CLIPS[ci][1] + dy;
                                    int n = 3 + (dx & 7);
                                    reset(&ca, bufA, CAMS[mi][0], CAMS[mi][1],
                                          CLIPS[ci][0], CLIPS[ci][1],
                                          CLIPS[ci][2], CLIPS[ci][3], palt_on);
                                    reset(&cb, bufB, CAMS[mi][0], CAMS[mi][1],
                                          CLIPS[ci][0], CLIPS[ci][1],
                                          CLIPS[ci][2], CLIPS[ci][3], palt_on);
                                    spr_reference(&ca, &sh, n, x, y, KEYS[ki],
                                                  scale, flip);
                                    moy_spr(&cb, &sh, n, x, y, KEYS[ki],
                                            scale, flip);
                                    cases++;
                                    if (memcmp(bufA, bufB, sizeof(bufA)) != 0) {
                                        if (fails < 6) {
                                            printf("MISMATCH clip=(%d,%d,%d,%d) "
                                                   "cam=(%d,%d) palt=%d key=%d "
                                                   "scale=%d flip=%d at (%d,%d)\n",
                                                   CLIPS[ci][0], CLIPS[ci][1],
                                                   CLIPS[ci][2], CLIPS[ci][3],
                                                   CAMS[mi][0], CAMS[mi][1],
                                                   palt_on, KEYS[ki], scale, flip,
                                                   x, y);
                                        }
                                        fails++;
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    printf("spr scale sweep: %d cases, %d mismatches\n", cases, fails);
    return fails ? 1 : 0;
}
