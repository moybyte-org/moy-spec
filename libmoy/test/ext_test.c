/* The host-dependent core verbs: view, background and the layers.
 *
 * What is at stake is not "do the verbs work" but the rule that keeps them out
 * of SPEC.md 10: each does something truthful on a host that implements
 * nothing, so its ABSENCE can never be observed and a cart needs no guard. So
 * the first thing this asserts is PRESENCE -- a console with no callbacks at
 * all still gives a cart every name, and an unguarded cart runs on it -- and
 * only then that a console with callbacks draws the right pixels.
 *
 * The one thing a host may still refuse is a SECOND layer, and that surfaces
 * as nil from make_layer: an allocation that failed, not a verb that is gone.
 *
 *   cc -DMOY_WITH_LUA -Iinclude -Ivendor/lua test/ext_test.c src/moy_lua.o \
 *      vendor/lua/*.o libmoy.a -lm
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"

#include "moy.h"

static int fails;

static void ok(const char *what, int cond)
{
    printf("  %-4s %s\n", cond ? "ok" : "FAIL", what);
    if (!cond) fails++;
}

/* -- a host that implements both extensions ------------------------------- */

static moy_pixel layer_mem[64 * 32];
static int layers_asked, view_w, view_h, bg_col = -1;

static moy_pixel *h_layer_new(void *user, int w, int h)
{
    (void)user;
    layers_asked++;
    if ((size_t)w * (size_t)h > sizeof layer_mem / sizeof layer_mem[0]) return NULL;
    return layer_mem;
}
static void h_view(void *user, int w, int h) { (void)user; view_w = w; view_h = h; }
static void h_background(void *user, int c) { (void)user; bg_col = c; }

static lua_State *boot(moy_console *con, moy_canvas *cv, moy_pixel *fb,
                       moy_sheet *sh, moy_map *mp, int with_ext)
{
    lua_State *L;
    moy_canvas_init(cv, fb, 32, 16);
    moy_console_init(con, cv, sh, mp);
    if (with_ext) {
        con->host.layer_new = h_layer_new;
        con->host.view = h_view;
        con->host.background = h_background;
    }
    L = luaL_newstate();
    moy_lua_open(L, con);
    return L;
}

static int has_global(lua_State *L, const char *name)
{
    int t = lua_getglobal(L, name);
    lua_pop(L, 1);
    return t != LUA_TNIL;
}

static int run(lua_State *L, const char *src)
{
    char err[192];
    if (luaL_loadstring(L, src) != LUA_OK || lua_pcall(L, 0, 0, 0) != LUA_OK) {
        printf("  load failed: %s\n", lua_tostring(L, -1));
        return 0;
    }
    if (moy_lua_init(L, err, sizeof err) != 0) { printf("  _init: %s\n", err); return 0; }
    if (moy_lua_update(L, 1.0f / 30.0f, err, sizeof err) != 0) { printf("  _update: %s\n", err); return 0; }
    if (moy_lua_draw(L, err, sizeof err) != 0) { printf("  _draw: %s\n", err); return 0; }
    return 1;
}

int main(void)
{
    static moy_pixel fb[32 * 16];
    static uint8_t sheet_pix[MOY_SHEET_W * MOY_SHEET_H];
    static uint8_t cells[4 * 4];
    moy_console con;
    moy_canvas cv;
    moy_sheet sh;
    moy_map mp;
    lua_State *L;

    moy_sheet_init(&sh, sheet_pix);
    moy_map_init(&mp, cells, 4, 4);

    puts("a host implementing NOTHING still offers every global");
    L = boot(&con, &cv, fb, &sh, &mp, 0);
    /* All three are core now, so all three exist even here; what a host
     * without an allocator cannot do is HAND OUT a layer, which is nil rather
     * than a missing name. */
    ok("make_layer present", has_global(L, "make_layer"));
    ok("draw_layer present", has_global(L, "draw_layer"));
    ok("view present even unimplemented", has_global(L, "view"));
    ok("background present even unimplemented", has_global(L, "background"));
    ok("core verbs still present", has_global(L, "rect") && has_global(L, "spr"));
    ok("an UNGUARDED cart runs on a host implementing neither",
       run(L, "function _init() view(16, 8) background(3) end\n"
              "function _draw() rect(0, 0, 4, 4, 9) end\n"));
    ok("libmoy cleared to the declared background", fb[31] == 3);
    ok("...and the cart drew over it", fb[0] == 9);
    ok("the declaration was recorded for a host that polls",
       con.view_w == 16 && con.view_h == 8);
    ok("make_layer with no allocator returns nil, not an error",
       run(L, "got = 'unset'\n"
              "function _draw() local L = make_layer(8, 8)\n"
              "  got = (L == nil) and 'nil' or 'layer' end\n"));
    { int t = lua_getglobal(L, "got");
      ok("...and the cart saw the nil", t == LUA_TSTRING
         && strcmp(lua_tostring(L, -1), "nil") == 0);
      lua_pop(L, 1); }
    lua_close(L);

    puts("a host WITH an allocator hands out real layers");
    L = boot(&con, &cv, fb, &sh, &mp, 1);
    puts("layers draw, and composite where the window says");
    ok("cart ran",
       run(L, "function _init()\n"
              "  L = make_layer(64, 32)\n"
              "  L:cls(0)\n"
              "  L:rect(8, 0, 8, 32, 9)\n"     /* a stripe at layer x 8..15 */
              "end\n"
              "function _update(dt) view(16, 8) background(4) end\n"
              "function _draw() cls(2) draw_layer(L, 8, 0) end\n"));
    ok("host was asked for one layer", layers_asked == 1);
    /* The window starts at layer x=8, so the stripe lands at screen x 0..7. */
    ok("window offset honoured", fb[0] == 9 && fb[7] == 9 && fb[8] != 9);
    ok("layer drew on ITS surface, not the screen", layer_mem[8] == 9);
    ok("view relayed", view_w == 16 && view_h == 8);
    ok("background relayed", bg_col == 4);

    puts("a layer speaks the whole drawing API, on its own state");
    ok("methods and state are the layer's",
       run(L, "function _draw()\n"
              "  local M = make_layer(32, 16)\n"
              "  M:cls(0) M:camera(4, 0) M:rect(4, 0, 2, 2, 7) M:camera()\n"
              "  cls(0) draw_layer(M, 0, 0)\n"
              "end\n"));
    ok("layer camera applied to the layer", fb[0] == 7);
    ok("screen camera untouched by the layer", cv.cam_x == 0 && cv.cam_y == 0);
    lua_close(L);

    puts("a console with NO sheet and NO map is a console, not a crash");
    /* moy_console holds both by pointer, so "the host has neither yet" is a
     * legal state -- a brand-new project, or an embedder that wants only the
     * geometry verbs. It used to be a segfault: the verbs handed the NULL
     * straight to a raster that dereferences what it is given. Per SPEC.md
     * 10's rule for anything the host did not supply, they degrade truthfully
     * instead -- an absent sheet reads as empty tiles, an absent map as empty
     * cells, both indistinguishable from data a cart simply has not drawn. */
    moy_canvas_init(&cv, fb, 32, 16);
    moy_console_init(&con, &cv, NULL, NULL);
    L = luaL_newstate();
    moy_lua_open(L, &con);
    memset(fb, 5, sizeof fb);
    ok("every sheet/map verb runs",
       run(L, "function _draw()\n"
              "  spr(1, 0, 0)  sspr(0, 0, 8, 8, 0, 0)\n"
              "  map(0, 0)     tline(0, 0, 8, 8, 0, 0, 65536, 0)\n"
              "  mset(1, 1, 3)\n"
              "  GOT = mget(1, 1)\n"
              "end\n"));
    ok("...drawing nothing rather than something", fb[0] == 5 && fb[64] == 5);
    { lua_getglobal(L, "GOT");
      ok("mget answers -1, the same nothing it answers off a real map",
         (int)lua_tointeger(L, -1) == -1);
      lua_pop(L, 1); }
    lua_close(L);

    printf("%s (%d failure%s)\n", fails ? "FAILED" : "all ok", fails,
           fails == 1 ? "" : "s");
    return fails ? 1 : 0;
}
