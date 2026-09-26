/* The direct-colour raster under its own names, for a program that links both
 * builds of libmoy.
 *
 * A player that runs Lua carts on the index build (SPEC.md 1) and compiled
 * carts on the direct-colour one (proposals/wasm-runtime.md: a palette blit's
 * 256 colours do not fit 64 indices) compiles src/moy_canvas.c and
 * src/moy_sprite.c twice. The second copy, and every file that calls it, is
 * built with
 *
 *     -DMOY_PIXEL_RGB565 -include port/moy565.h
 *
 * and this header renames each of the raster's external symbols to moy565_*,
 * so the two copies link side by side and neither build's source changes.
 * Each copy is only ever called from files built the same way, because
 * moy_canvas is a different struct in each.
 *
 * What is NOT here is shared on purpose: src/moy_data.c (the palette and the
 * font are pixel-independent) and src/moy_audio.c are compiled once. A raster
 * function missing from this list is defined by both copies, and the link
 * fails naming it -- which is the guard.
 */

#ifndef MOY565_H_INCLUDED
#define MOY565_H_INCLUDED

#define moy_blit_window       moy565_blit_window
#define moy_camera            moy565_camera
#define moy_camera_reset      moy565_camera_reset
#define moy_canvas_init       moy565_canvas_init
#define moy_canvas_wire       moy565_canvas_wire
#define moy_circ              moy565_circ
#define moy_circb             moy565_circb
#define moy_clip              moy565_clip
#define moy_clip_reset        moy565_clip_reset
#define moy_cls               moy565_cls
#define moy_console_init      moy565_console_init
#define moy_fillp             moy565_fillp
#define moy_fillp_reset       moy565_fillp_reset
#define moy_line              moy565_line
#define moy_map_draw          moy565_map_draw
#define moy_map_draw_layers   moy565_map_draw_layers
#define moy_map_init          moy565_map_init
#define moy_mget              moy565_mget
#define moy_mset              moy565_mset
#define moy_oval              moy565_oval
#define moy_ovalb             moy565_ovalb
#define moy_pal               moy565_pal
#define moy_palette_rgb565    moy565_palette_rgb565
#define moy_palette_rgb888    moy565_palette_rgb888
#define moy_pal_reset         moy565_pal_reset
#define moy_pal_screen        moy565_pal_screen
#define moy_pal_screen_reset  moy565_pal_screen_reset
#define moy_palt              moy565_palt
#define moy_palt_reset        moy565_palt_reset
#define moy_pget              moy565_pget
#define moy_pix               moy565_pix
#define moy_print             moy565_print
#define moy_rect              moy565_rect
#define moy_rectb             moy565_rectb
#define moy_reset_state       moy565_reset_state
#define moy_rnd               moy565_rnd
#define moy_sheet_init        moy565_sheet_init
#define moy_sheet_pget        moy565_sheet_pget
#define moy_sheet_pset        moy565_sheet_pset
#define moy_spr               moy565_spr
#define moy_srand             moy565_srand
#define moy_sspr              moy565_sspr
#define moy_tline             moy565_tline
#define moy_tri               moy565_tri
#define moy_trib              moy565_trib

#endif /* MOY565_H_INCLUDED */
