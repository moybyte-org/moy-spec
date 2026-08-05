-- Every verb family, thirty frames, quit. The ship gate for the desktop
-- players: the conformance goldens judge correctness, this proves the
-- PACKAGED binary reaches every verb path and exits cleanly on its own OS.
local n = 0

function _update(dt)
  n = n + 1
  if n > 30 then quit() end
end

function _draw()
  cls(1)
  camera(0, 0)
  clip(0, 0, 320, 240)
  pal(7, 7)
  palt(0, true)
  pix(5, 5, 7)
  line(0, 0, 319, 239, 6)
  rect(10, 10, 20, 12, 3)
  rectb(10, 30, 20, 12, 4)
  circ(50, 60, 8, 8)
  circb(70, 60, 8, 9)
  tri(100, 20, 160, 30, 130, 80, 8)
  trib(180, 20, 240, 30, 210, 80, 10)
  spr(0, 100, 100)
  sspr(0, 0, 8, 8, 120, 100, 16, 16)
  map(0, 0, 4, 4, 140, 100)
  tline(0, 100, 319, 100, 0, 0, 65536, 0)
  print("smoke " .. tostring(btn("a")) .. " " .. tostring(pmem(0)), 8, 8, 7)
end
