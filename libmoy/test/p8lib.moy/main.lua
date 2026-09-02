-- The p8 stdlib verbs libmoy promotes into C (libmoy/src/moy_p8.c), held
-- equal to the SHIM'S OWN LUA -- the fallback in p8_lua_port.py, transcribed
-- here as the reference. The shim aliases to the C when a host offers it, so
-- the two answers a cart can get must be one answer; this is what says so.
--
-- Runs under run_cart, which opens the machine. A failed check is an error()
-- naming it, so `make p8-test` is red by name.
local function check(name, ok)
  if not ok then error("p8 stdlib: " .. name, 0) end
end

local function same(name, a, b)
  if a ~= b then
    error("p8 stdlib: " .. name .. ": C " .. tostring(a) .. ", Lua " .. tostring(b), 0)
  end
end

-- ---- the shim's Lua, verbatim -------------------------------------------
local tremove = table.remove

local function L_add(t, v) t[#t + 1] = v return v end
local function L_del(t, v)
  for i = 1, #t do
    if t[i] == v then tremove(t, i) return end
  end
end
local function L_all(t)
  if t == nil then return function() return nil end end
  local i = 0
  local v
  return function()
    if t[i] == v then i = i + 1 end
    v = t[i]
    return v
  end
end
local function L_foreach(t, f) for v in L_all(t) do f(v) end end
local function L_count(t, v)
  if v == nil then return #t end
  local n = 0
  for i = 1, #t do if t[i] == v then n = n + 1 end end
  return n
end
local function L_deli(t, i)
  if t == nil then return nil end
  if i == nil then i = #t end
  local v = t[i]
  table.remove(t, i)
  return v
end

-- ---- the two lanes, over the same script --------------------------------
-- A script is a list of steps run against a fresh table by each lane; the
-- lanes are then compared element by element, with what each visit SAW.
local function seq(n)
  local t = {}
  for i = 1, n do t[i] = "e" .. i end
  return t
end

local function dump(t)
  local s = "#" .. #t
  for i = 1, #t do s = s .. "," .. tostring(t[i]) end
  return s
end

-- Every iteration shape a p8 cart uses, deletions included: the current
-- element, the next one, the last one, all of them, none.
local function run_lane(all_, foreach_, del_, deli_, kill)
  local t = seq(6)
  local seen = ""
  local n = 0
  for v in all_(t) do
    n = n + 1
    seen = seen .. "|" .. tostring(v)
    kill(t, v, n, del_, deli_)
  end
  return seen .. " -> " .. dump(t)
end

local KILLS = {
  ["nothing"]      = function() end,
  ["the current"]  = function(t, v, _, del_) del_(t, v) end,
  ["every other"]  = function(t, v, n, del_) if n % 2 == 1 then del_(t, v) end end,
  ["the last"]     = function(t, _, _, _, deli_) deli_(t) end,
  ["the first"]    = function(t, _, _, _, deli_) if #t > 0 then deli_(t, 1) end end,
}

function _init()
  check("the machine is open", __moy_all ~= nil and __moy_foreach ~= nil)

  for name, kill in pairs(KILLS) do
    same("all() deleting " .. name,
         run_lane(__moy_all, __moy_foreach, __moy_del, __moy_deli, kill),
         run_lane(L_all, L_foreach, L_del, L_deli, kill))
  end

  -- foreach walks what all() walks
  for name, kill in pairs(KILLS) do
    local function lane(all_, foreach_, del_, deli_)
      local t, seen, n = seq(6), "", 0
      foreach_(t, function(v)
        n = n + 1
        seen = seen .. "|" .. tostring(v)
        kill(t, v, n, del_, deli_)
      end)
      return seen .. " -> " .. dump(t)
    end
    same("foreach() deleting " .. name,
         lane(__moy_all, __moy_foreach, __moy_del, __moy_deli),
         lane(L_all, L_foreach, L_del, L_deli))
  end

  -- the empty and the absent
  check("all(nil) is an empty loop", __moy_all(nil)() == nil)
  local n = 0
  for _ in __moy_all(nil) do n = n + 1 end
  for _ in __moy_all({}) do n = n + 1 end
  __moy_foreach(nil, function() n = n + 1 end)
  __moy_foreach({}, function() n = n + 1 end)
  check("nothing to iterate iterates nothing", n == 0)

  -- a list holding nil-adjacent values: false and 0 are elements, nil ends it
  local t = {false, 0, ""}
  local seen = ""
  for v in __moy_all(t) do seen = seen .. "|" .. tostring(v) end
  same("false and 0 are elements", seen, "|false|0|")

  -- add / count / del / deli against the Lua
  local a, b = {}, {}
  for i = 1, 5 do
    same("add returns what it added", __moy_add(a, i * 2), L_add(b, i * 2))
  end
  same("add builds the same list", dump(a), dump(b))
  same("count()", __moy_count(a), L_count(b))
  __moy_add(a, 4) L_add(b, 4)
  same("count(t, v)", __moy_count(a, 4), L_count(b, 4))
  same("count of an absent value", __moy_count(a, 99), L_count(b, 99))
  __moy_del(a, 4) L_del(b, 4)
  same("del removes the FIRST match", dump(a), dump(b))
  __moy_del(a, 99) L_del(b, 99)
  same("del of an absent value", dump(a), dump(b))
  same("deli()", __moy_deli(a), L_deli(b))
  same("deli(t, i)", __moy_deli(a, 2), L_deli(b, 2))
  same("deli left the same list", dump(a), dump(b))
  check("deli(nil) is nil", __moy_deli(nil) == nil)

  -- __eq and __index are honoured: all() compares with `==` and reads with
  -- `t[i]`, so a cart's own metatables answer as they did in Lua. Lua answers
  -- `x == x` by identity and never reaches __eq, so it takes a SHIFTED table
  -- to put two different objects on either side of the comparison.
  local function eq_lane(all_, del_)
    local eqs = 0
    local mt = {__eq = function() eqs = eqs + 1 return true end}
    local u = {setmetatable({}, mt), setmetatable({}, mt), setmetatable({}, mt)}
    local m = 0
    for v in all_(u) do m = m + 1 del_(u, v) end
    return m .. "/" .. eqs .. "/" .. #u
  end
  same("__eq decides whether the cursor advances",
       eq_lane(__moy_all, __moy_del), eq_lane(L_all, L_del))

  local function index_lane(all_)
    local seen, back = "", {"a", "b", "c"}
    local u = setmetatable({}, {__index = function(_, k) return back[k] end})
    for v in all_(u) do seen = seen .. "|" .. tostring(v) end
    return seen
  end
  same("__index feeds the walk", index_lane(__moy_all), index_lane(L_all))
  check("__index really was the only source", index_lane(__moy_all) == "|a|b|c")
end

function _draw() cls(1) print("p8 stdlib: ok", 4, 60, 11) quit() end
