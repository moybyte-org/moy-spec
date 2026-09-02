-- The PICO-8 memory map (libmoy/src/moy_p8.c), every mirrored region both
-- ways. Runs under run_cart, which opens the machine; a failed check is an
-- error() naming it, so `make p8-test` is red by name.
--
-- The assets are arithmetic so the seed is checkable: sheet pixel i is
-- (i * 7) & 15, map cell i holds tile (i % 7), tile n's flags are n & 0xff.
local function check(name, ok)
  if not ok then error("p8 memory map: " .. name, 0) end
end

function _init()
  check("the machine is open", __moy_peek ~= nil and __moy_p8print ~= nil)
  -- seeding
  check("sheet seeded (two pixels a byte, low nibble left)",
        __moy_peek(0) == (0 | (7 << 4)) and __moy_peek(1) == (14 | (5 << 4)))
  check("map seeded (tile+1 undone)", __moy_peek(0x2000) == 0 and __moy_peek(0x2001) == 1)
  check("flags seeded", __moy_peek(0x3005) == 5 and __moy_peek(0x30ff) == 255)
  check("draw palette reads the canvas", __moy_peek(0x5f00) == 0 and __moy_peek(0x5f07) == 7)
  palt(0, true)
  check("palt shows as bit 4", __moy_peek(0x5f00) == 0x10)
  check("screen palette seeded", __moy_peek(0x5f17) == 7)
  check("clip seeded", __moy_peek(0x5f22) == 128 and __moy_peek(0x5f23) == 128)
  -- the screen is the canvas
  __moy_poke(0x6000, 0x87)
  check("poke lands on the canvas", pix(0, 0) == 7 and pix(1, 0) == 8)
  pix(2, 0, 11) pix(3, 0, 12)
  check("peek reads the canvas", __moy_peek(0x6001) == (11 | (12 << 4)))
  __moy_memset(0x6000, 0x33, 8192)
  check("memset fills the screen", pix(127, 127) == 3 and pix(64, 64) == 3)
  -- sheet and map write-through
  __moy_poke(0x2005, 42)
  check("map write-through", mget(5, 0) == 42)
  __moy_poke(0x1000, 0x21)
  check("shared rows: sheet AND map row 32", mget(0, 32) == 0x21 and sget(0, 64) == 1 and sget(1, 64) == 2)
  __moy_poke(0x0000, 0xf9)
  check("sheet write-through", sget(0, 0) == 9 and sget(1, 0) == 15)
  __moy_memcpy(0, 0x6000, 8192)
  check("screen -> sheet copy", __moy_peek(0x1fff) == 0x33 and sget(127, 127) == 3)
  -- flags both ways
  __moy_poke(0x3005, 0x80)
  check("flags write-through", fget(5) == 0x80 and fget(5, 7) == true)
  fset(6, 0x41)
  check("fset is visible in memory", __moy_peek(0x3006) == 0x41)
  -- draw palette both ways
  __moy_poke(0x5f01, 9)
  pix(5, 5, 1)
  check("draw palette write-through", pix(5, 5) == 9)
  pal(2, 12)
  palt(2, true)
  check("pal/palt read back", __moy_peek(0x5f02) == (12 | 0x10))
  __moy_poke(0x5f03, 0x45)
  check("the draw palette is four bits", __moy_peek(0x5f03) == 5)
  __moy_poke(0x5f13, 0x85)
  check("the screen palette names the secret sixteen", __moy_peek(0x5f13) == 0x85)
  __moy_poke(0x5f03, 0x83)
  check("bit 7 in the draw palette is transparency too", __moy_peek(0x5f03) == 0x13)
  pal()
  pal() palt()          -- the console's own resets: the p8 shim's pal() does both at once
  check("pal() resets what memory reads", __moy_peek(0x5f01) == 1 and __moy_peek(0x5f03) == 3)
  -- screen palette both ways
  pal(4, 14, 1)
  check("screen palette read back", __moy_peek(0x5f14) == 14)
  __moy_poke(0x5f15, 2)
  pal()
  check("screen palette reset", __moy_peek(0x5f15) == 5)
  -- camera and clip
  camera(300, -5)
  check("camera read back", __moy_peek(0x5f28) == 44 and __moy_peek(0x5f29) == 1
        and __moy_peek(0x5f2a) == 251 and __moy_peek(0x5f2b) == 255)
  camera()
  __moy_poke(0x5f20, 10) __moy_poke(0x5f21, 20) __moy_poke(0x5f22, 30) __moy_poke(0x5f23, 40)
  local ok = true
  cls(0)
  rect(0, 0, 128, 128, 7)
  ok = pix(5, 5) == 0 and pix(15, 25) == 7 and pix(35, 25) == 0
  clip()
  check("clip write-through", ok)
  -- ROM
  __moy_memcpy(0x4300, 0x0, 16)
  __moy_poke(0x4300, 200)
  check("plain RAM", __moy_peek(0x4300) == 200 and __moy_peek(0x4301) == __moy_peek(1))
  __moy_poke(0x2005, 0)
  __moy_reload(0x2000, 0x2000, 0x1000)
  check("reload restores the map from ROM", mget(5, 0) == 5)
  __moy_poke(0x2005, 77)
  __moy_cstore(0x2000, 0x2000, 0x1000)
  __moy_poke(0x2005, 0)
  __moy_reload()
  check("cstore rewrites the ROM", mget(5, 0) == 77)
  -- bounds
  check("addresses wrap at 16 bits, as PICO-8's do",
        __moy_peek(-1) == __moy_peek(0xffff) and __moy_peek(70000) == __moy_peek(70000 & 0xffff))
  __moy_poke(70000, 1)
  __moy_memcpy(0xfff0, 0, 100)
  __moy_memset(0xfff0, 1, 100)
  -- the font
  cls(0)
  local x = __moy_p8print("A\nB", 10, 10, 7)
  check("p8print advances 4 a glyph and 6 a line", x == 14 and pix(10, 17) == 7 and pix(10, 11) == 7)
  cls(0)
  __moy_p8print(string.char(135), 0, 0, 8)      -- the heart, 7 wide
  check("p8print draws the wide glyphs", pix(2, 2) == 8 and pix(3, 4) == 8)
end

function _draw() cls(1) print("p8 memory map: ok", 4, 60, 11) quit() end
