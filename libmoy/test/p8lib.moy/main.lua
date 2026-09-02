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

-- ---- the memory verbs ---------------------------------------------------
-- The shim's Lua over the one-byte C, against the C that now takes the whole
-- form. Both lanes write the same scratch region (0x3100-0x5eff is plain RAM),
-- so each case runs twice from the same seed and the bytes are compared.
local cpeek, cpoke = __moy_peek, __moy_poke
local mfloor = math.floor

local function fl(v)
  if type(v) ~= "number" then v = tonumber(v) or 0 end
  return mfloor(v)
end
local function L_peek(a, n)
  if n == nil or n <= 1 then return cpeek(a) end
  local out = {}
  for i = 0, fl(n) - 1 do out[i + 1] = cpeek(a + i) end
  return table.unpack(out)
end
local function L_poke(a, v, ...)
  cpoke(a, v or 0)
  local n = select("#", ...)
  for i = 1, n do cpoke(a + i, select(i, ...) or 0) end
end
local function L_peek2(a) a = fl(a) local v = cpeek(a) | (cpeek(a + 1) << 8)
  if v >= 0x8000 then v = v - 0x10000 end return v end
local function L_poke2(a, v) a, v = fl(a), fl(v or 0) & 0xffff
  cpoke(a, v & 0xff) cpoke(a + 1, (v >> 8) & 0xff) end
local function L_peek4(a) a = fl(a)
  local v = cpeek(a) | (cpeek(a+1) << 8) | (cpeek(a+2) << 16) | (cpeek(a+3) << 24)
  return v / 65536.0 end
local function L_poke4(a, v) a = fl(a)
  local raw = fl((v or 0) * 65536) & 0xffffffff
  cpoke(a, raw & 0xff) cpoke(a+1, (raw>>8) & 0xff)
  cpoke(a+2, (raw>>16) & 0xff) cpoke(a+3, (raw>>24) & 0xff) end

local SCRATCH = 0x4400
local function seed()
  for i = 0, 31 do cpoke(SCRATCH + i, (i * 37) & 0xff) end
end
local function snap()
  local s = ""
  for i = 0, 31 do s = s .. cpeek(SCRATCH + i) .. "," end
  return s
end
-- Two runs from the same seed: what each lane WROTE and what it RETURNED.
local function lane(f, ...)
  seed()
  local r = {f(...)}
  local out = "#" .. #r
  for i = 1, #r do out = out .. ":" .. tostring(r[i]) end
  return out .. " " .. snap()
end

function mem_checks()
  check("the memory verbs are the C ones", __moy_peek2 ~= nil and __moy_poke4 ~= nil)

  -- poke: one byte, a run, and every coercion p8 does on the way in. `n` is
  -- the ARGUMENT COUNT, because a trailing nil the caller typed and one it
  -- did not are different calls to poke's vararg tail.
  local POKES = {
    {n = 2, SCRATCH, 1}, {n = 2, SCRATCH}, {n = 2, SCRATCH, 300},
    {n = 2, SCRATCH, -1}, {n = 2, SCRATCH, 3.7}, {n = 2, SCRATCH, "12"},
    {n = 2, SCRATCH, true}, {n = 1, SCRATCH},
    {n = 5, SCRATCH, 1, 2, 3, 4}, {n = 4, SCRATCH, 1, nil, 3},
    {n = 6, SCRATCH + 2, 9, 9, 9, 9, 9},
    {n = 3, SCRATCH + 0.5, 7, 8}, {n = 3, SCRATCH - 0.5, 7, 8},
    {n = 2, SCRATCH + 0.5, 7}, {n = 2, "17408", 5},
    {n = 2, SCRATCH + 65536, 6}, {n = 2, -1, 4},
  }
  for k, c in ipairs(POKES) do
    same("poke case " .. k, lane(__moy_poke, table.unpack(c, 1, c.n)),
                            lane(L_poke, table.unpack(c, 1, c.n)))
  end

  -- peek: the single form, the multi form, and n's own coercions
  for _, n in ipairs({-1, 0, 1, 2, 2.9, 5, 0.5}) do
    same("peek(a, " .. n .. ")",
         lane(__moy_peek, SCRATCH, n), lane(L_peek, SCRATCH, n))
  end
  same("peek(a)", lane(__moy_peek, SCRATCH), lane(L_peek, SCRATCH))
  same("peek(a) at the top of memory", lane(__moy_peek, 0xffff), lane(L_peek, 0xffff))
  same("peek(a, n) over the wrap", lane(__moy_peek, 0xfffe, 4), lane(L_peek, 0xfffe, 4))

  -- peek2 / poke2: int16 LE, and its wrap
  for _, v in ipairs({0, 1, -1, 32767, -32768, 65535, 70000, 1.75, -1.75}) do
    same("poke2(" .. v .. ")", lane(L_poke2, SCRATCH, v), lane(__moy_poke2, SCRATCH, v))
    L_poke2(SCRATCH, v)
    same("peek2 of " .. v, __moy_peek2(SCRATCH), L_peek2(SCRATCH))
  end
  same("poke2 of nil", lane(__moy_poke2, SCRATCH), lane(L_poke2, SCRATCH))

  -- peek4 / poke4: the 16.16 word, where a p8 number's representation shows
  -- An INTEGER out of 16.16's range wraps in both lanes (Lua multiplies
  -- integers with a 32-bit wrap, and so does the C). A FLOAT out of range
  -- parts them: math.floor hands back the float it cannot make an integer of
  -- and `&` refuses it, so the shim RAISES where the C wraps -- its own case
  -- below, since a raise is not a semantics worth keeping.
  for _, v in ipairs({0, 1, -1, 0.5, -0.5, 1/256, 255.99, -255.99,
                      32767.5, -32768.0, 3, 100000, -100000}) do
    same("poke4(" .. v .. ")", lane(L_poke4, SCRATCH, v), lane(__moy_poke4, SCRATCH, v))
    L_poke4(SCRATCH, v)
    same("peek4 of " .. v, __moy_peek4(SCRATCH), L_peek4(SCRATCH))
    check("peek4 of " .. v .. " keeps its type",
          math.type(__moy_peek4(SCRATCH)) == math.type(L_peek4(SCRATCH)))
  end
  same("poke4 of nil", lane(__moy_poke4, SCRATCH), lane(L_poke4, SCRATCH))
  same("poke4 of an integer", lane(__moy_poke4, SCRATCH, 3), lane(L_poke4, SCRATCH, 3))
  __moy_poke4(SCRATCH, 100000)          -- past 16.16: defined, and no error
  check("poke4 past 16.16 wraps into the signed word",
        __moy_peek4(SCRATCH) == ((100000 + 32768) % 65536) - 32768)
  __moy_poke4(SCRATCH, -32768.5)
  check("a FLOAT past 16.16 wraps too", __moy_peek4(SCRATCH) == 32767.5)
  check("the Lua it replaced raised instead", not pcall(L_poke4, SCRATCH, -32768.5))

  -- memcpy / memset kept their `len or 0`
  seed()
  local fresh = snap()
  __moy_memcpy(SCRATCH + 8, SCRATCH, nil)
  __moy_memset(SCRATCH + 8, 1, nil)
  same("memcpy/memset of no length write nothing", snap(), fresh)
  __moy_memset(SCRATCH, 0x5a, 4)
  check("memset writes", cpeek(SCRATCH) == 0x5a and cpeek(SCRATCH + 3) == 0x5a
        and cpeek(SCRATCH + 4) ~= 0x5a)
end

-- ---- the number verbs ---------------------------------------------------
-- Value AND type: math.floor hands back an integer when one fits and a float
-- when it does not, and the shim reads that difference back (p8str prints 3
-- rather than 3.0, the bit verbs branch on math.type).
local msin, mcos, matan = math.sin, math.cos, math.atan
local mabs, mmin, mmax = math.abs, math.min, math.max

local function L_fl(v)
  if type(v) ~= "number" then v = tonumber(v) or 0 end
  return mfloor(v)
end
local function L_flr(v) return mfloor(v or 0) end
local function L_abs(v) return mabs(v or 0) end
local function L_min(a, b) return mmin(a or 0, b or 0) end
local function L_max(a, b) return mmax(a or 0, b or 0) end
local function L_mid(a, b, c) return L_max(L_min(a, b), L_min(L_max(a, b), c)) end
local function L_sgn(x) if (x or 0) < 0 then return -1 end return 1 end
local function L_sin(t) return -msin((t or 0) * 6.283185307179586) end
local function L_cos(t) return mcos((t or 0) * 6.283185307179586) end
local function L_atan2(dx, dy)
  return matan(-(dy or 0), dx or 0) / 6.283185307179586 % 1
end
local function L_tonum(v)
  if type(v) == "number" then return v end
  return tonumber(v)
end

-- Everything a p8 cart puts through these, the coercions included.
local ARGS = {
  0, 1, -1, 2, 7, 255, 3.7, -3.7, 0.5, -0.5, 0.25, 1/3,
  32767, -32768, 2147483647, -2147483648, 16777217, 1e30, -1e30,
  1/0, -1/0, "3", "3.7", "0x10", "abc", "", true, false, {},
}
local NARGS = 29                   -- #ARGS stops at the first nil; there is none

local function call1(f, ...)
  local ok, v = pcall(f, ...)
  if not ok then return "ERR" end
  return tostring(v) .. "/" .. tostring(math.type(v))
end

function num_checks()
  check("the number verbs are the C ones", __moy_flr ~= nil and __moy_mid ~= nil)

  local ONE = {
    {"fl", __moy_fl, L_fl}, {"flr", __moy_flr, L_flr}, {"abs", __moy_abs, L_abs},
    {"sgn", __moy_sgn, L_sgn}, {"sin", __moy_sin, L_sin},
    {"cos", __moy_cos, L_cos}, {"tonum", __moy_tonum, L_tonum},
  }
  for _, v in ipairs(ONE) do
    for i = 1, NARGS do
      same(v[1] .. "(" .. tostring(ARGS[i]) .. ")",
           call1(v[2], ARGS[i]), call1(v[3], ARGS[i]))
    end
    same(v[1] .. "() with no argument at all", call1(v[2]), call1(v[3]))
  end

  local TWO = {
    {"min", __moy_min, L_min}, {"max", __moy_max, L_max},
    {"atan2", __moy_atan2, L_atan2},
  }
  for _, v in ipairs(TWO) do
    for i = 1, NARGS do
      for j = 1, NARGS do
        same(v[1] .. "(" .. tostring(ARGS[i]) .. ", " .. tostring(ARGS[j]) .. ")",
             call1(v[2], ARGS[i], ARGS[j]), call1(v[3], ARGS[i], ARGS[j]))
      end
      same(v[1] .. "(" .. tostring(ARGS[i]) .. ")", call1(v[2], ARGS[i]), call1(v[3], ARGS[i]))
    end
  end

  -- mid takes three, so sweep the numeric ones in all orders rather than the
  -- full cube of coercions.
  for i = 1, 20 do
    for j = 1, 20 do
      for k = 1, 20 do
        same("mid", call1(__moy_mid, ARGS[i], ARGS[j], ARGS[k]),
                    call1(L_mid, ARGS[i], ARGS[j], ARGS[k]))
      end
    end
  end
  for i = 1, NARGS do
    same("mid of one", call1(__moy_mid, ARGS[i]), call1(L_mid, ARGS[i]))
    same("mid of two", call1(__moy_mid, ARGS[i], 5), call1(L_mid, ARGS[i], 5))
  end

  -- min/max hand back the ARGUMENT, so an integer stays an integer
  check("min keeps the argument's type", math.type(__moy_min(1, 1.0)) == "integer")
  check("max keeps the argument's type", math.type(__moy_max(1.0, 1)) == "float")
end

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

  mem_checks()
  num_checks()
end

function _draw() cls(1) print("p8 stdlib: ok", 4, 60, 11) quit() end
