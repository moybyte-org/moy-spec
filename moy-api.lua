---@meta
-- moy console API stubs (EmmyLua annotations) -- editor support only, never
-- executed. Keep this file in your cart folder: the Lua language server
-- (VS Code "Lua" extension et al.) indexes it for autocomplete, hover docs
-- and typo squiggles on every console verb. The behavioural contract is the
-- moy spec (SPEC.md); one line here per verb, the spec is the truth.
--
-- Every verb below is CORE (runs on any conforming console) unless marked:
--   EXTENSION: <name> -- standard extension (SPEC.md 10); declare it in your
--                        manifest's "extensions" or hosts may lack it
--   DRAFT 6.1         -- provisional (SPEC.md 6.1): names/signatures still
--                        moving, NOT core 0.1, may be dropped entirely
--
-- Only core and the standard extensions are listed. A console may offer more
-- (the reference one does: a pointer verb, palette colour names, painted-image
-- and spreadsheet/document assets); those belong to that console, so they are
-- deliberately absent here -- a cart calling them is non-portable.
--
-- Screen: 320x240 by default -- a manifest may declare "canvas": "160x120" or
-- "128x128" (SPEC.md 3.1) -- palette-indexed (64 colours, indices 0-63; 0-15
-- are the classic base 16). Sheet: 512 8x8 tiles (16 per row). Origin
-- top-left, +x right, +y down. A cart defines up to three globals the console
-- calls: _init(), _update(dt), _draw().

---Canvas width in pixels (320 unless the manifest declares a smaller canvas).
W = 320
---Canvas height in pixels (240 unless the manifest declares a smaller canvas).
H = 240

-- --- clear / pixels ---------------------------------------------------------

---Clear the whole screen to colour `c` (default 0).
---@param c? integer palette index 0-63
function cls(c) end

---Set one pixel.
---@param x integer
---@param y integer
---@param c integer palette index 0-63
function pix(x, y, c) end

---Line from (x0,y0) to (x1,y1).
---@param x0 integer
---@param y0 integer
---@param x1 integer
---@param y1 integer
---@param c integer
function line(x0, y0, x1, y1, c) end

-- --- shapes -----------------------------------------------------------------

---Filled rectangle.
---@param x integer
---@param y integer
---@param w integer
---@param h integer
---@param c integer
function rect(x, y, w, h, c) end

---Rectangle border (1px).
---@param x integer
---@param y integer
---@param w integer
---@param h integer
---@param c integer
function rectb(x, y, w, h, c) end

---Filled circle.
---@param cx integer
---@param cy integer
---@param r integer
---@param c integer
function circ(cx, cy, r, c) end

---Circle outline.
---@param cx integer
---@param cy integer
---@param r integer
---@param c integer
function circb(cx, cy, r, c) end

---Filled triangle. Provisional (SPEC.md 6.1).
---@param x1 integer
---@param y1 integer
---@param x2 integer
---@param y2 integer
---@param x3 integer
---@param y3 integer
---@param c integer
function tri(x1, y1, x2, y2, x3, y3, c) end

---Triangle outline. Provisional (SPEC.md 6.1).
---@param x1 integer
---@param y1 integer
---@param x2 integer
---@param y2 integer
---@param x3 integer
---@param y3 integer
---@param c integer
function trib(x1, y1, x2, y2, x3, y3, c) end

---Textured line: draw exactly line()'s pixels, sampling the MAP as a
---virtual texture. u,v,du,dv are 16.16 FIXED-POINT integers (float * 65536);
---before each pixel the texel (u>>16, v>>16) is sampled, then u,v advance by
---du,dv. Empty map cells draw nothing. The Mode 7 verb: one call per
---scanline, perspective lives in how du,dv change BETWEEN scanlines.
---Provisional (SPEC.md 6.1) -- in moycore and libmoy, golden-checked;
---device kernels pending.
---@param x0 integer
---@param y0 integer
---@param x1 integer
---@param y1 integer
---@param u integer 16.16 map-pixel x at the first pixel
---@param v integer 16.16 map-pixel y at the first pixel
---@param du integer 16.16 step per drawn pixel
---@param dv integer 16.16 step per drawn pixel
---@param colorkey? integer transparent colour (-1 = none)
function tline(x0, y0, x1, y1, u, v, du, dv, colorkey) end

-- --- sprites / map ----------------------------------------------------------

---Draw sheet tile `n` (8x8) at (x,y).
---@param n integer tile id
---@param x integer
---@param y integer
---@param colorkey? integer transparent colour (-1 = none)
---@param scale? integer integer scale (default 1)
---@param flip? integer 0 none, 1 horizontal, 2 vertical, 3 both
function spr(n, x, y, colorkey, scale, flip) end

---Stretch-blit a sheet PIXEL region (sx,sy,sw,sh) to a dw x dh screen rect --
---arbitrary (non-integer) scaling; the textured-slice verb (a raycaster's
---wall column is sspr with dw=1). Provisional (SPEC.md 6.1).
---@param sx integer sheet pixel x
---@param sy integer sheet pixel y
---@param sw integer
---@param sh integer
---@param dx integer screen x
---@param dy integer screen y
---@param dw? integer dest width (default sw)
---@param dh? integer dest height (default sh)
---@param colorkey? integer
---@param flip? integer
function sspr(sx, sy, sw, sh, dx, dy, dw, dh, colorkey, flip) end

---Blit a w x h CELL region of the tilemap (top-left cell mx,my) at screen
---(sx,sy). Tiles are the 8x8 sheet sprites; scale=2 makes 16px world tiles.
---@param mx? integer
---@param my? integer
---@param w? integer cells wide (default: whole map)
---@param h? integer cells high
---@param sx? integer
---@param sy? integer
---@param colorkey? integer
---@param scale? integer
function map(mx, my, w, h, sx, sy, colorkey, scale) end

---Read a tilemap cell.
---@param x integer
---@param y integer
---@return integer tile id, -1 outside the map
function mget(x, y) end

---Write a tilemap cell.
---@param x integer
---@param y integer
---@param tile integer
function mset(x, y, tile) end

-- --- text / draw state ------------------------------------------------------

---Print `s` at (x,y) in the 8x8 system font.
---@param s string|number
---@param x integer
---@param y integer
---@param c integer
function print(s, x, y, c) end

---Clip all drawing to a rect; clip() with no args resets.
---@param x? integer
---@param y? integer
---@param w? integer
---@param h? integer
function clip(x, y, w, h) end

---Set the camera offset (subtracted from every draw); camera() resets.
---@param x? integer
---@param y? integer
function camera(x, y) end

---Remap palette index c0 -> c1 for subsequent draws; pal() resets all.
---@param c0? integer
---@param c1? integer
function pal(c0, c1) end

---Mark colour `c` transparent (on=true) for sprite blits; palt() resets.
---@param c? integer
---@param on? boolean
function palt(c, on) end

-- --- input ------------------------------------------------------------------

---Is a button held this frame? Names: "left" "right" "up" "down" "a" "b",
---plus "run" on hosts that have it (SPEC.md 7.3).
---@param name string
---@param player? integer extra controller slot (default 0 = the console)
---@return boolean
function btn(name, player) end

---Was the button PRESSED this frame (the up->down edge)?
---@param name string
---@param player? integer
---@return boolean
function btnp(name, player) end

---Connected player count (>= 1).
---@return integer
function players() end

---Touch state: x, y, tapped (press edge), held -- or nil without a pointer.
---@return integer? x, integer? y, boolean? tapped, boolean? held
function touch() end

---Last typed key's ASCII code (0 = none), or test a specific code:
---key(string.byte("a")).
---@param code? integer
---@return integer|boolean
function key(code) end

---Key PRESSED this frame (the 0->code edge); same shape as key().
---@param code? integer
---@return integer|boolean
function keyp(code) end

---Switch the keyboard to TEXT input (clean typeable ASCII incl. autorepeat
---delete) or back to game mode. A textmode(true) cart MUST provide its own
---exit via quit().
---@param on? boolean
function textmode(on) end

-- --- system -----------------------------------------------------------------

---Milliseconds since the cart started.
---@return integer
function time() end

---A random float in [0, n) (default n = 1.0).
---@param n? number
---@return number
function rnd(n) end

---Floor to an integer.
---@param x number
---@return integer
function flr(x) end

---Read a config value from the cart's config.json (the player-tunable knobs).
---@param k string
---@param default? any
---@return any
function cfg(k, default) end

---Persistent memory: pmem(i) reads slot i, pmem(i, v) writes it. Survives
---restarts (host permitting).
---@param i integer slot index
---@param v? integer
---@return integer
function pmem(i, v) end

---End this cart and return to whoever launched it. The ONLY exit for a
---textmode(true) cart.
function quit() end

---Declare a logical viewport: the console scales the centered w x h region of
---the canvas to the screen (a 128x128 game fills the display). view() resets.
---EXTENSION: viewport.
---@param w? integer
---@param h? integer
function view(w, h) end

-- --- audio ------------------------------------------------------------------

---Play sound effect `n` (from the cart's sound bank).
---@param n integer
---@param chan? integer channel 0-3 (default: auto)
function sfx(n, chan) end

---A simple beep.
---@param freq number Hz
---@param dur? number seconds (default 0.15)
function beep(freq, dur) end

---Start music track `track`.
---@param track integer
---@param loop? boolean default true
function music(track, loop) end

---Stop the music.
function music_stop() end

---Stop sound on `chan` (or all channels).
---@param chan? integer
function sound_stop(chan) end

---Master volume 0.0-1.0.
---@param level number
function volume(level) end

-- --- layers / images --------------------------------------------------------

---@class MoyLayer
---@field W integer
---@field H integer
local MoyLayer = {}
---Draw into the layer with the same verbs (l:spr(...), l:cls(...)).
---@param img integer tile id
---@param x? integer
---@param y? integer
---@param colorkey? integer
---@param scale? integer
---@param flip? integer
function MoyLayer:spr(img, x, y, colorkey, scale, flip) end
---@param c? integer
function MoyLayer:cls(c) end

---An off-screen canvas (w x h, may be wider than the screen): pre-render a
---level ONCE, then window-copy per frame with draw_layer -- the 60fps
---scroller pattern. EXTENSION: layers.
---@param w integer
---@param h integer
---@return MoyLayer
function make_layer(w, h) end

---Blit the visible window of `layer` at camera offset (cam_x, cam_y).
---EXTENSION: layers.
---@param layer MoyLayer
---@param cam_x? integer
---@param cam_y? integer
function draw_layer(layer, cam_x, cam_y) end

---Declare a backdrop the console repaints automatically each frame -- a
---colour index, or a layer to pin behind everything. EXTENSION: layers.
---@param x integer|MoyLayer
function background(x) end
