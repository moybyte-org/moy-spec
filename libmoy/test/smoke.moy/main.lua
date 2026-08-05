-- EVERY core verb, thirty frames, quit. The ship gate for the desktop
-- players: the conformance goldens judge correctness, this proves the
-- PACKAGED binary reaches every verb path and exits cleanly on its own OS.
-- Every symbol the API declares is called, because a verb the binding forgot
-- to register is nil -- which is how a Celeste port crashed on its pause
-- menu (music_stop) while every golden stayed green.
local n = 0

function _update(dt)
  n = n + 1
  sfx(0)
  music(0)
  beep(440, 0.05)
  volume(7)
  sound_stop()
  music_stop()
  key(90)
  keyp()
  textmode(false)
  local tx = touch()
  mset(0, 0, 1)
  if mget(0, 0) ~= 1 then error("mget") end
  if flr(1.5) ~= 1 then error("flr") end
  if players() < 1 then error("players") end
  local r = rnd(1)
  local ms = time()
  cfg("smoke", "default")
  btnp("a")
  pmem(0, pmem(0))
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
