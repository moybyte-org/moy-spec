/* libmoy on ESP-IDF: the whole port, and nothing that isn't the port.
 *
 * A moy console needs exactly four things from a platform (SPEC.md 7.3, 9):
 * pixels out, buttons in, a clock, and 256 slots of persistence. This file
 * implements those four against real IDF APIs -- esp_timer, GPIO, NVS -- runs
 * a cart, and resolves the framebuffer to RGB565 ready for a panel. It is the
 * ESP-IDF twin of port/sdl2/main.c, and about the same length, which is the
 * point being made: the porting surface is small on purpose.
 *
 * What is deliberately absent is the panel driver. There is no such thing as
 * "the" ESP32 display: an esp_lcd MIPI-DSI panel, a parallel RGB one and an
 * SPI module all take the same `uint16_t *` and differ in every other respect.
 * So this stops at the buffer and marks the one line you add. Everything BEFORE
 * that line is board-independent, and everything after it is your board.
 *
 * Builds for esp32p4 in CI (.github/workflows/libmoy.yml), which is what keeps
 * the component honest. See ../README.md for what running it still owes you.
 */

#include <stdio.h>
#include <string.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_heap_caps.h"
#include "driver/gpio.h"
#include "nvs.h"
#include "nvs_flash.h"

#ifdef MOY_WITH_LUA
#include "lua.h"
#include "lauxlib.h"
#endif

#include "moy.h"

static const char *TAG = "moy";

/* -- the cart ------------------------------------------------------------ *
 *
 * Embedded as a string so the example has no filesystem to set up. A real host
 * reads main.lua out of a .moy directory (SPEC.md 3) on SD, SPIFFS or a
 * partition -- the binding does not care where the bytes came from.
 *
 * This one touches every host duty below, so a build that links but wires a
 * callback to the wrong thing still shows up in the log. */
#ifdef MOY_WITH_LUA
static const char CART[] =
    "local frames = 0\n"
    "local boots = 0\n"
    "function _init()\n"
    "  boots = pmem(0) + 1\n"           /* persistence, read */
    "  pmem(0, boots)\n"                /* persistence, write */
    "end\n"
    "function _update(dt)\n"
    "  frames = frames + 1\n"
    "  if btn(4) then frames = frames + 10 end\n"   /* buttons */
    "end\n"
    "function _draw()\n"
    "  cls(1)\n"
    "  rect(8, 8, 60, 24, 12)\n"
    "  circ(160, 120, 40 + (frames % 8), 8)\n"
    "  print('boot ' .. boots, 12, 14, 7)\n"
    "  print('t=' .. flr(time()), 12, 30, 7)\n"      /* the clock */
    "end\n";
#endif

/* -- memory (SPEC.md 1.1) ------------------------------------------------ *
 *
 * libmoy never allocates: every buffer below is placed by the host, which is
 * the whole reason placement is a decision you get to make. On a PSRAM part
 * mark these EXT_RAM_BSS_ATTR and keep internal SRAM for the Lua VM's hot
 * allocations -- the reference console measured an all-PSRAM heap at roughly 2x
 * slower cart logic. A cart can observe none of this. */
static uint8_t framebuffer[MOY_W * MOY_H];                    /*  75 KB */
static uint8_t sheet_pix[MOY_SHEET_W * MOY_SHEET_H];          /*  32 KB */
static uint8_t map_cells[MOY_MAP_MAX * MOY_MAP_MAX];          /*  16 KB */
static uint16_t *rgb565;                                      /* 150 KB, see below */

/* -- 1. buttons in (SPEC.md 7.3) ----------------------------------------- *
 *
 * Seven logical buttons, active-low with internal pull-ups, and -1 for one this
 * board does not have. Only `run` may be missing: SPEC.md 7.3 requires a cart
 * to be playable with the other six. Your board's numbers go here; a touch
 * region or an I2C expander substitutes just as well, since the console only
 * ever asks "is LEFT down". */
static const int BTN_GPIO[MOY_BTN_COUNT] = {
    -1, -1, -1, -1,     /* left, right, up, down */
    -1, -1,             /* a, b */
    -1                  /* run -- optional */
};

static uint8_t btn_prev[MOY_BTN_COUNT];
static uint8_t btn_now[MOY_BTN_COUNT];

static void buttons_init(void)
{
    for (int i = 0; i < MOY_BTN_COUNT; i++) {
        if (BTN_GPIO[i] < 0) continue;
        gpio_config_t cfg = {
            .pin_bit_mask = 1ULL << BTN_GPIO[i],
            .mode = GPIO_MODE_INPUT,
            .pull_up_en = GPIO_PULLUP_ENABLE,
            .pull_down_en = GPIO_PULLDOWN_DISABLE,
            .intr_type = GPIO_INTR_DISABLE,
        };
        ESP_ERROR_CHECK(gpio_config(&cfg));
    }
}

/* Sampled once per tick, not per call: a cart may ask btn() several times in a
 * frame and must get the same answer each time (SPEC.md 5). */
static void buttons_poll(void)
{
    memcpy(btn_prev, btn_now, sizeof btn_now);
    for (int i = 0; i < MOY_BTN_COUNT; i++)
        btn_now[i] = (BTN_GPIO[i] >= 0 && gpio_get_level((gpio_num_t)BTN_GPIO[i]) == 0);
}

static int h_btn(void *u, moy_button b, int player)
{
    (void)u;
    if (player > 1) return 0;               /* one pad on this board */
    return btn_now[b];
}

static int h_btnp(void *u, moy_button b, int player)
{
    (void)u;
    if (player > 1) return 0;
    return btn_now[b] && !btn_prev[b];
}

static int h_players(void *u) { (void)u; return 1; }

/* -- 2. a clock ---------------------------------------------------------- *
 *
 * Milliseconds since the cart started, not since boot: SPEC.md 9 says time()
 * begins at zero for the cart, and a cart that sees 40 000 ms on its first
 * frame will mis-time everything it does. */
static int64_t start_us;

static uint32_t h_time_ms(void *u)
{
    (void)u;
    return (uint32_t)((esp_timer_get_time() - start_us) / 1000);
}

/* -- 3. persistence (SPEC.md 9) ------------------------------------------ *
 *
 * 256 signed 32-bit slots. Cached in RAM and written through to NVS, because a
 * cart may write a slot every frame and flash will not survive that: NVS wear-
 * levels, but 30 commits a second still burns the sector. Cheap and correct
 * here; a host that wants fewer writes coalesces on a timer or on quit. */
static nvs_handle_t pmem_nvs;
static int32_t pmem_cache[256];

static void pmem_init(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    ESP_ERROR_CHECK(err);
    ESP_ERROR_CHECK(nvs_open("moy_pmem", NVS_READWRITE, &pmem_nvs));

    for (int i = 0; i < 256; i++) {
        char key[8];
        snprintf(key, sizeof key, "m%d", i);
        if (nvs_get_i32(pmem_nvs, key, &pmem_cache[i]) != ESP_OK)
            pmem_cache[i] = 0;              /* SPEC.md 9: unset reads as 0 */
    }
}

static int32_t h_pmem_get(void *u, int slot) { (void)u; return pmem_cache[slot]; }

static void h_pmem_set(void *u, int slot, int32_t value)
{
    char key[8];
    (void)u;
    if (pmem_cache[slot] == value) return;  /* no write, no wear */
    pmem_cache[slot] = value;
    snprintf(key, sizeof key, "m%d", slot);
    if (nvs_set_i32(pmem_nvs, key, value) == ESP_OK)
        nvs_commit(pmem_nvs);
}

/* -- 4. quit (SPEC.md 9) ------------------------------------------------- */

static volatile int quit_requested;
static void h_quit(void *u) { (void)u; quit_requested = 1; }

/* -- the cart, in whichever language this build has ---------------------- *
 *
 * CONFIG_MOY_WITH_LUA is a real fork, so the example takes both sides of it and
 * CI builds both. With Lua you have a console and carts are data; without it
 * libmoy is a raster library your firmware calls, the VM's ~200 KB of flash is
 * gone, and everything below this seam -- the host callbacks, the frame loop,
 * the palette resolve -- is identical either way. */

#ifdef MOY_WITH_LUA

static lua_State *L;

static int cart_open(moy_console *con, char *err, size_t errlen)
{
    L = luaL_newstate();
    if (!L) { snprintf(err, errlen, "no lua_State"); return 1; }
    moy_lua_open(L, con);                   /* the verbs, and the 4.1 sandbox */

    if (luaL_loadbuffer(L, CART, sizeof CART - 1, "main.lua") != LUA_OK ||
        lua_pcall(L, 0, 0, 0) != LUA_OK) {
        /* SPEC.md 4.3: surface it with the cart's line number, never swallow it. */
        snprintf(err, errlen, "%s", lua_tostring(L, -1));
        return 1;
    }
    return moy_lua_init(L, err, errlen);
}

static int cart_update(moy_console *con, float dt, char *err, size_t errlen)
{
    (void)con;
    return moy_lua_update(L, dt, err, errlen);
}

static int cart_draw(moy_console *con, char *err, size_t errlen)
{
    (void)con;
    return moy_lua_draw(L, err, errlen);
}

static void cart_close(void) { lua_close(L); }

#else   /* CONFIG_MOY_WITH_LUA=n -- the same cart, written in C */

static int frames;
static int32_t boots;

static int cart_open(moy_console *con, char *err, size_t errlen)
{
    (void)err; (void)errlen;
    boots = con->host.pmem_get(con->host.user, 0) + 1;
    con->host.pmem_set(con->host.user, 0, boots);
    return 0;
}

static int cart_update(moy_console *con, float dt, char *err, size_t errlen)
{
    (void)dt; (void)err; (void)errlen;
    frames++;
    if (con->host.btn(con->host.user, MOY_BTN_A, 1)) frames += 10;
    return 0;
}

static int cart_draw(moy_console *con, char *err, size_t errlen)
{
    char line[32];
    int n;
    (void)err; (void)errlen;

    moy_cls(con->canvas, 1);
    moy_rect(con->canvas, 8, 8, 60, 24, 12);
    moy_circ(con->canvas, 160, 120, 40 + (frames % 8), 8);

    n = snprintf(line, sizeof line, "boot %d", (int)boots);
    moy_print(con->canvas, (const uint8_t *)line, (size_t)n, 12, 14, 7);
    n = snprintf(line, sizeof line, "t=%u",
                 (unsigned)(con->host.time_ms(con->host.user) / 1000));
    moy_print(con->canvas, (const uint8_t *)line, (size_t)n, 12, 30, 7);
    return 0;
}

static void cart_close(void) { }

#endif

/* -- the console --------------------------------------------------------- */

void app_main(void)
{
    static moy_canvas canvas;
    static moy_sheet sheet;
    static moy_map map;
    static moy_console con;
    char err[256] = {0};
    int frame = 0;

    ESP_LOGI(TAG, "libmoy %s on ESP-IDF", MOY_VERSION);

    /* PSRAM if the board has it, internal if not: the resolved frame is 150 KB
     * and is written once per frame and read by DMA, which is exactly the
     * traffic PSRAM is good at. */
    rgb565 = heap_caps_malloc(MOY_W * MOY_H * sizeof(uint16_t),
                              MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
    if (!rgb565) rgb565 = heap_caps_malloc(MOY_W * MOY_H * sizeof(uint16_t),
                                           MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT);
    if (!rgb565) { ESP_LOGE(TAG, "no room for the resolved frame"); return; }

    buttons_init();
    pmem_init();
    start_us = esp_timer_get_time();

    moy_canvas_init(&canvas, framebuffer, MOY_W, MOY_H);
    moy_sheet_init(&sheet, sheet_pix);
    moy_map_init(&map, map_cells, 20, 15);
    moy_console_init(&con, &canvas, &sheet, &map);

    con.host.btn      = h_btn;
    con.host.btnp     = h_btnp;
    con.host.players  = h_players;
    con.host.time_ms  = h_time_ms;
    con.host.pmem_get = h_pmem_get;
    con.host.pmem_set = h_pmem_set;
    con.host.quit     = h_quit;
    /* sfx and music stay NULL: SPEC.md 8.3 makes silence a valid rendering, so
     * a board with no audio is still conforming and the cart never finds out. */

    if (cart_open(&con, err, sizeof err)) {
        ESP_LOGE(TAG, "cart: %s", err);
        return;
    }

    while (!quit_requested) {
        int64_t t0 = esp_timer_get_time();

        buttons_poll();
        moy_reset_state(&canvas);           /* draw state is per-frame (SPEC.md 6) */

        if (cart_update(&con, 1.0f / 30.0f, err, sizeof err)) {
            ESP_LOGE(TAG, "_update: %s", err); break;
        }
        if (cart_draw(&con, err, sizeof err)) {
            ESP_LOGE(TAG, "_draw: %s", err); break;
        }

        /* Indices to pixels. NULL takes the spec's palette (SPEC.md 2); pass a
         * cart-supplied one here if the manifest carried it (2.2). */
        moy_palette_rgb565(&canvas, NULL, rgb565);

        /* >>> YOUR BOARD, one line: <<<
         *   esp_lcd_panel_draw_bitmap(panel, 0, 0, MOY_W, MOY_H, rgb565);
         * Everything above this comment is board-independent. */

        if (++frame % 30 == 0)
            ESP_LOGI(TAG, "frame %d, %lld us/frame, %d bytes free",
                     frame, esp_timer_get_time() - t0,
                     (int)heap_caps_get_free_size(MALLOC_CAP_INTERNAL));

        /* SPEC.md 5's 30 Hz tick. vTaskDelay is the crude version; a real host
         * paces off the panel's vsync so the frame lands with the refresh. */
        int64_t spent_ms = (esp_timer_get_time() - t0) / 1000;
        if (spent_ms < 33) vTaskDelay(pdMS_TO_TICKS(33 - spent_ms));
    }

    ESP_LOGI(TAG, "cart exited after %d frames", frame);
    cart_close();
}
