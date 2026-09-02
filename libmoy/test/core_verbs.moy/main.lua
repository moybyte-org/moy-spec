-- Every core verb exists as a global. Run it on a player; it errors, loudly and
-- by name, if the player is missing one.
--
-- This cart exists because a player shipped without `make_layer` for twelve
-- commits and nothing noticed. The conformance suite could not: its scenes are
-- recorded rasters and no scene uses a layer, so a host can pass all of them
-- with a verb table full of holes. examples/verbs.moy does reach every verb,
-- but SPEC.md 11 has it looked at rather than diffed, so the only thing that
-- caught it was a person playing screen 8.
--
-- It asserts EXISTENCE, not behaviour -- the goldens are for behaviour. That is
-- the whole gap: nil is not a wrong pixel, it is no pixel and a dead cart.

local CORE = {
  -- SPEC.md 6, drawing
  "cls", "background", "view", "pix", "line", "rect", "rectb", "circ",
  "circb", "oval", "ovalb", "print", "camera", "clip", "pal", "palt", "fillp",
  -- SPEC.md 6, layers: core since 1.1's floor reserves one full-screen buffer
  "make_layer", "draw_layer",
  -- SPEC.md 7.1 / 7.2, sprites and map
  "spr", "map", "mget", "mset", "sget", "sset",
  -- SPEC.md 7.3, input. touch/key/keyp/textmode are hardware-optional and are
  -- deliberately absent here; a host without a pointer owes you nothing.
  "btn", "btnp", "players",
  -- SPEC.md 8.2, audio. Required to EXIST even on a silent host (8.2: a host
  -- with no audio hardware implements these as no-ops and still conforms).
  "sfx", "beep", "music", "music_stop", "sound_stop", "volume",
  -- SPEC.md 9, state and utility
  "time", "pmem", "cfg", "rnd", "srand", "flr", "quit",
}

-- SPEC.md 4.1's LIBRARIES, which the sandbox check in CI can only prove
-- absent, never present: a host that forgot to open one passes every golden
-- and kills the first cart that reaches for a coroutine.
local LIBS = { "math", "string", "table", "coroutine" }

-- SPEC.md 6.1 is PROVISIONAL and not part of core 0.2, so its verbs are not
-- required and their absence is not a failure: tri, trib, sspr, tline.
local PROVISIONAL = { "tri", "trib", "sspr", "tline" }

function _init()
  local missing = {}
  for i = 1, #CORE do
    if _G[CORE[i]] == nil then missing[#missing + 1] = CORE[i] end
  end
  for i = 1, #LIBS do
    if type(_G[LIBS[i]]) ~= "table" then missing[#missing + 1] = LIBS[i] end
  end
  -- W and H are values, not functions (SPEC.md 9)
  if type(W) ~= "number" then missing[#missing + 1] = "W" end
  if type(H) ~= "number" then missing[#missing + 1] = "H" end
  if #missing > 0 then
    error("missing core verbs: " .. table.concat(missing, " "), 0)
  end
  -- Behaviour a golden cannot see either: the READ form of pix (SPEC.md 6)
  -- and a coroutine that actually yields.
  pix(1, 1, 7)
  if pix(1, 1) ~= 7 then error("pix(x, y) does not read back the index", 0) end
  local co = coroutine.create(function(a) local b = coroutine.yield(a + 1) return b * 2 end)
  local ok1, v1 = coroutine.resume(co, 1)
  local ok2, v2 = coroutine.resume(co, 5)
  if not (ok1 and v1 == 2 and ok2 and v2 == 10 and coroutine.status(co) == "dead") then
    error("coroutine does not run", 0)
  end
  pal(7, 9, 1)
  pal()
  srand(7)
  local r1 = rnd(1000)
  srand(7)
  if rnd(1000) ~= r1 then error("srand does not replay the sequence", 0) end
end

function _draw()
  cls(1)
  print("core verb table complete", 8, 8, 11)
  local have = {}
  for i = 1, #PROVISIONAL do
    if _G[PROVISIONAL[i]] ~= nil then have[#have + 1] = PROVISIONAL[i] end
  end
  print("6.1 provisional present: " .. (#have > 0 and table.concat(have, " ")
                                        or "none"), 8, 20, 5)
  quit()
end
