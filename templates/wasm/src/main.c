/* {title}: a compiled moy cart (SPEC.md 16).
 *
 * The console calls three hooks, as it does a Lua cart's:
 *   _init()        once at start
 *   _update(dt)    every tick (dt in seconds)
 *   _draw()        every frame
 * and every verb is a function in moy_cart.h, imported from the console.
 *
 * What a compiled cart can do that a Lua one cannot is its own per-pixel work:
 * this one fills a whole frame of palette indices every _draw and hands it to
 * the console with moy_blit, then draws over it with the ordinary verbs.
 *
 * It also keeps a file (SPEC.md 16.12): manifest.json declares "saves/"
 * writable, B writes where the circle is, and the next time the cart starts
 * _init reads it back.
 *
 * `moy build` compiles src/ into main.wasm; `moy play` rebuilds it when you
 * save a file here, and reloads it. */
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "moy_cart.h"

#define W 320
#define H 240

static uint8_t frame[W * H];   /* one palette index a pixel, row-major */
static uint8_t palette[256 * 3]; /* the 256 colours this frame is shown in */
static uint8_t wave[256];      /* one period of a sine, 0-255 */

static float t;
static float x = W / 2, y = H / 2;
static int fps, frames, second_start;

static const char SAVE[] = "saves/circle.bin";
static int saved = 1, saved_at;   /* what the last save answered, and when */

MOY_EXPORT("_init") void init(void)
{
    for (int i = 0; i < 256; i++) {
        float a = (float)i * 6.2831853f / 256.0f;
        wave[i] = (uint8_t)(127.5f + 127.5f * sinf(a));
        palette[i * 3 + 0] = (uint8_t)(128 + 127 * sinf(a));
        palette[i * 3 + 1] = (uint8_t)(128 + 127 * sinf(a + 2.1f));
        palette[i * 3 + 2] = (uint8_t)(128 + 127 * sinf(a + 4.2f));
    }
    /* No save yet reads 0 bytes, and the circle starts in the middle. */
    float at[2];
    if (moy_read(SAVE, sizeof SAVE - 1, 0, at, sizeof at) == sizeof at) {
        x = at[0];
        y = at[1];
    }
}

MOY_EXPORT("_update") void update(float dt)
{
    float speed = 120 * dt;
    t += dt;
    if (moy_btn(MOY_LEFT, 0)) x -= speed;
    if (moy_btn(MOY_RIGHT, 0)) x += speed;
    if (moy_btn(MOY_UP, 0)) y -= speed;
    if (moy_btn(MOY_DOWN, 0)) y += speed;
    if (x < 8) x = 8;
    if (x > W - 8) x = W - 8;
    if (y < 8) y = 8;
    if (y > H - 8) y = H - 8;
    if (moy_btnp(MOY_B, 0)) {
        /* 0 when the file is written; -2 when the console has no room. */
        float at[2] = { x, y };
        saved = moy_write(SAVE, sizeof SAVE - 1, at, sizeof at);
        saved_at = moy_time();
    }
}

MOY_EXPORT("_draw") void draw(void)
{
    /* A plasma: three waves summed, per pixel, drifting with time. */
    int a = (int)(t * 60), b = (int)(t * 45), c = (int)(t * 30);
    for (int py = 0; py < H; py++) {
        uint8_t *row = frame + py * W;
        int wy = wave[(py + b) & 255];
        for (int px = 0; px < W; px++)
            row[px] = (uint8_t)(wave[(px + a) & 255] + wy + wave[(px + py + c) & 255]);
    }
    moy_blit(frame, palette);

    /* The verbs draw over the frame, in the cart's own 64 colours. */
    moy_circ((int)x, (int)y, 8, 8);
    moy_circb((int)x, (int)y, 8, 7);

    frames++;
    if (moy_time() - second_start >= 1000) {
        fps = frames;
        frames = 0;
        second_start = moy_time();
    }
    char line[40];
    int n = snprintf(line, sizeof line, "{title}  %d FPS", fps);
    if (n > (int)sizeof line - 1) n = (int)sizeof line - 1;
    moy_rect(4, 4, n * 8 + 4, 12, 0);
    moy_print(line, n, 6, 6, 7);
    moy_print("arrows move, B saves", 20, 8, 228, 7);
    if (saved != 1 && moy_time() - saved_at < 1500) {
        const char *said = saved == 0 ? "saved" : "not saved";
        moy_print(said, (int32_t)strlen(said), 220, 228, saved == 0 ? 11 : 8);
    }
}
