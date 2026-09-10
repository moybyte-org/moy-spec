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

-- btn/btnp coerce a numeric string (the size-coder's btn"1"); a string that
-- is no number is the no-argument bitfield form, never the O button.
local pb, pbp = rawget(_G, "__moy_p8_btn"), rawget(_G, "__moy_p8_btnp")
check("btn(\"1\") is button 1, not O", pb ~= nil and type(pb("1")) == "boolean" and pb("1") == pb(1))
check("btnp(\"5\") is button 5", pbp ~= nil and type(pbp("5")) == "boolean" and pbp("5") == pbp(5))
check("btn(\"zz\") is the bitfield form", pb ~= nil and type(pb("zz")) == "number" and pb("zz") == pb())
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

local E6, E2 = string.char(6), string.char(2)
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

-- ---- split --------------------------------------------------------------
-- PICO-8's own, and the one verb here a cart calls with a DIFFERENT NUMBER OF
-- ARGUMENTS from line to line: `split"1,2,3"` in a data table, `split(s, "|")`
-- parsing a save, `split(s, ",", false)` keeping text as text. The arity is
-- therefore part of the input and every sweep below varies it -- a C version
-- that reads its second argument after pushing anything sees the pushed value
-- there, and `split"91,51"` becomes a string cutting itself on its own text.

-- the shim's Lua, verbatim
local function L_split(s, sep, num)
  local out = {}
  if s == nil then return out end
  s = tostring(s)
  if num == nil then num = true end
  local function keep(part)
    out[#out + 1] = num and (tonumber(part) or part) or part
  end
  if type(sep) == "number" then
    local step = sep < 1 and 1 or mfloor(sep)
    if step ~= step then return out end
    if #s > 0 and step > #s then step = #s end
    for i = 1, #s, step do keep(string.sub(s, i, i + step - 1)) end
    return out
  end
  sep = sep or ","
  if sep == "" then sep = "," end
  local i = 1
  while true do
    local j = string.find(s, sep, i, true)
    if j then keep(string.sub(s, i, j - 1)) else keep(string.sub(s, i)) break end
    i = j + #sep
  end
  return out
end

-- The dump carries the TYPE of every part, because the whole point of the
-- conversion is that "1" comes back an integer and "1.0" a float.
local function dump_split(t)
  local s = "#" .. #t
  for i = 1, #t do
    s = s .. "|" .. tostring(t[i]) .. ":" .. tostring(math.type(t[i]))
  end
  return s
end

local function split_lane(f, ...)
  local ok, v = pcall(f, ...)
  if not ok then return "ERR" end
  if type(v) ~= "table" then return "NOT A TABLE: " .. tostring(v) end
  return dump_split(v)
end

local SUBJ = {
  "", "1", "1,2", "1,2,3", ",", ",,", ",1", "1,", "a,b,,c,",
  "  1 , 2  ", "0x10,1e3,12.,.5,-0,nan,inf,0x.8", "1,2\n3", "abc",
  "aXbXXc", "XX", "//a//b//", "a\0b,c", "91,51,1,3,2,5", "-1,-2.5,+3",
  "1;2;3", "true,false,nil", "0,00,0.0,1e0",
  0, 7, -3, 3.5, -0.5, 1/0, true, false,
  setmetatable({}, {__tostring = function() return "m,e,t,a" end}),
}
local NSUBJ = 32                   -- #SUBJ stops at a nil; there is none

local SEPS = {
  ",", "", "X", "XX", "//", ";", "\0", "2", "1,",
  1, 2, 3, 4, 0, -1, 0.5, 2.5, 7.9, 1e9, 0/0, 1/0,
  true, false, {},
}
local NSEPS = 24

function split_checks()
  check("split is the C one", __moy_split ~= nil)

  -- THE ONE-ARGUMENT CALL, named because it is the bug this verb shipped
  -- with: the subject read as its own separator answers {"",""} where the
  -- cart wanted {91,51}. Every data row in a ported cart is this shape.
  same("split\"91,51\" one argument", split_lane(__moy_split, "91,51"),
       split_lane(L_split, "91,51"))
  check("split\"91,51\" is the two numbers",
        dump_split(__moy_split("91,51")) == "#2|91:integer|51:integer")
  check("split\"abc\" is one part", dump_split(__moy_split("abc")) == "#1|abc:nil")
  check("split() with nothing at all is empty", #__moy_split() == 0)

  -- The cross product, at all three arities. `nil` passed explicitly and an
  -- argument left off are the same thing to this verb, and both are swept:
  -- an implementation that tells them apart is wrong in one of the two.
  for i = 1, NSUBJ do
    local s, name = SUBJ[i], "split(" .. tostring(SUBJ[i])
    same(name .. ")", split_lane(__moy_split, s), split_lane(L_split, s))
    same(name .. ", nil)", split_lane(__moy_split, s, nil),
         split_lane(L_split, s, nil))
    same(name .. ", nil, nil)", split_lane(__moy_split, s, nil, nil),
         split_lane(L_split, s, nil, nil))
    for j = 1, NSEPS do
      local sep, n2 = SEPS[j], name .. ", " .. tostring(SEPS[j])
      same(n2 .. ")", split_lane(__moy_split, s, sep), split_lane(L_split, s, sep))
      same(n2 .. ", true)", split_lane(__moy_split, s, sep, true),
           split_lane(L_split, s, sep, true))
      same(n2 .. ", false)", split_lane(__moy_split, s, sep, false),
           split_lane(L_split, s, sep, false))
      same(n2 .. ", 0)", split_lane(__moy_split, s, sep, 0),
           split_lane(L_split, s, sep, 0))
      same(n2 .. ", nil)", split_lane(__moy_split, s, sep, nil),
           split_lane(L_split, s, sep, nil))
    end
  end

  -- FUZZ. Subjects built from the bytes a separator is made of, so the
  -- interesting cases -- a separator that is the whole subject, a run of
  -- separators, a partial match that must not cut -- come up by themselves.
  -- The argument COUNT is drawn like everything else.
  local fz = 20260909
  local function frnd(n)
    fz = (fz * 1103515245 + 12345) & 0x7fffffff
    return (fz >> 7) % n + 1
  end
  local ALPHA = {"a", "b", ",", ",", "X", "XX", "1", "23", "-4.5", ";", "\0", " ", "0x8"}
  for _ = 1, 6000 do
    local s = ""
    for _ = 1, frnd(9) - 1 do s = s .. ALPHA[frnd(#ALPHA)] end
    local nargs, sep, num = frnd(3), SEPS[frnd(NSEPS)], nil
    if frnd(4) == 1 then sep = nil end
    local m = frnd(5)
    if m == 1 then num = true elseif m == 2 then num = false
    elseif m == 3 then num = 0 end
    local name = "fuzz " .. nargs .. " " .. string.format("%q", s) ..
                 " " .. tostring(sep) .. " " .. tostring(num)
    if nargs == 1 then
      same(name, split_lane(__moy_split, s), split_lane(L_split, s))
    elseif nargs == 2 then
      same(name, split_lane(__moy_split, s, sep), split_lane(L_split, s, sep))
    else
      same(name, split_lane(__moy_split, s, sep, num),
           split_lane(L_split, s, sep, num))
    end
  end

  -- A long subject: the C walks it with memchr, the Lua with string.find, and
  -- 4,000 parts is more than any cart's data row but exercises the table
  -- growth both lanes do differently.
  local big = "0"
  for i = 1, 4000 do big = big .. "," .. i end
  same("a 4,000-part subject", split_lane(__moy_split, big), split_lane(L_split, big))
  same("a 4,000-part subject, unconverted", split_lane(__moy_split, big, ",", false),
       split_lane(L_split, big, ",", false))
end

-- ---- rnd / srand --------------------------------------------------------
-- The one pair where equality of the ANSWER is not enough: the generator is
-- gameplay, so the C has to walk the same sequence the shim's math.random
-- walked, draw for draw, from the same seed. Nothing else here would notice a
-- transcription that is uniform, well distributed and simply different.
local mrandom, mrandomseed = math.random, math.randomseed

-- the shim's Lua, verbatim (flr is the shim's global, math.floor(v or 0))
local function L_rnd(n)
  if type(n) == "table" then
    local c = #n
    if c == 0 then return nil end
    return n[mrandom(c)]
  end
  return mrandom() * (n or 1)
end
local function L_srand(x) return mrandomseed(L_flr(x)) end

-- Both lanes seeded alike, then drawn in lockstep. `~=` on the floats is bit
-- equality: a generator in [0,1) produces no NaN, so there is no value that
-- compares unequal to itself and hides a difference.
local function same_stream(name, s, n, arg)
  __moy_p8_srand(s)
  L_srand(s)
  for i = 1, n do
    local a, b = __moy_p8_rnd(arg), L_rnd(arg)
    if a ~= b or math.type(a) ~= math.type(b) then
      error("p8 stdlib: " .. name .. " seed " .. tostring(s) .. " draw " .. i ..
            ": C " .. tostring(a) .. "/" .. tostring(math.type(a)) ..
            ", Lua " .. tostring(b) .. "/" .. tostring(math.type(b)), 0)
    end
  end
end

function rand_checks()
  check("rnd/srand are the C ones",
        __moy_p8_rnd ~= nil and __moy_p8_srand ~= nil)

  -- THE PROOF. Eight seeds, 20,000 draws each: the plain float form, which is
  -- lmathlib's I2d over the top FIGS bits, so a wrong shift or a wrong scale
  -- shows on draw one and a wrong state update shows within a few.
  for _, s in ipairs({0, 1, -1, 42, 2147483647, -2147483648, 1234567, 65536}) do
    same_stream("rnd()", s, 20000, nil)
  end
  -- ...and the same seeds again through the SCALED form, which multiplies,
  -- and through the table form, which projects into [1, #t] and retries when
  -- the interval is not a power of two (3, 5, 7, 10 and 100 all retry).
  for _, s in ipairs({0, 7, -13, 99991}) do
    same_stream("rnd(n)", s, 4000, 128)
    same_stream("rnd(-n)", s, 2000, -3.5)
    same_stream("rnd(str)", s, 2000, "3")
    for _, c in ipairs({1, 2, 3, 5, 7, 10, 100}) do
      local t = {}
      for i = 1, c do t[i] = "e" .. i end
      same_stream("rnd(#" .. c .. ")", s, 2000, t)
    end
  end
  -- Reseeding MID-STREAM: the state has to come back to the same place, not
  -- merely start there.
  __moy_p8_srand(5) L_srand(5)
  for _ = 1, 100 do __moy_p8_rnd() L_rnd() end
  same_stream("reseeded mid-stream", 5, 2000, nil)

  -- srand's own answer: `return mrandomseed(...)` hands back both seed words.
  -- Errors compare as "ERR", the file's own convention: a C verb's message
  -- carries no source location and the shim's does, and neither is the thing
  -- under test -- that both REFUSE the same arguments is.
  local function call2(f, ...)
    local ok, u, v = pcall(f, ...)
    if not ok then return "ERR" end
    return tostring(u) .. "/" .. tostring(math.type(u)) .. "/" ..
           tostring(v) .. "/" .. tostring(math.type(v))
  end
  for i = 1, NARGS do
    local c = call2(__moy_p8_srand, ARGS[i])
    same("srand(" .. tostring(ARGS[i]) .. ") returns", c,
         call2(L_srand, ARGS[i]))
    if c ~= "ERR" then                 -- it seeded: the streams must agree
      for _ = 1, 50 do
        local x, y = __moy_p8_rnd(), L_rnd()
        check("srand(" .. tostring(ARGS[i]) .. ") left the same state", x == y)
      end
    end
  end
  same("srand() with no argument at all", call1(__moy_p8_srand), call1(L_srand))

  -- rnd's coercions and refusals, the argument sweep both lanes share. Each
  -- case reseeds so the comparison is of the ANSWER, not of where the two
  -- streams happen to stand.
  for i = 1, NARGS do
    __moy_p8_srand(i) L_srand(i)
    same("rnd(" .. tostring(ARGS[i]) .. ")",
         call1(__moy_p8_rnd, ARGS[i]), call1(L_rnd, ARGS[i]))
  end
  same("rnd() with no argument at all",
       (function() __moy_p8_srand(1) L_srand(1)
          local a, b = __moy_p8_rnd(), L_rnd()
          return a == b end)(), true)

  -- A table is a DIFFERENT VERB wearing the name, and its metamethods answer:
  -- #t through __len, t[i] through __index, both in both lanes.
  local back = {"a", "b", "c", "d", "e"}
  local mt = {__len = function() return 5 end,
              __index = function(_, k) return back[k] end}
  same_stream("rnd(t) through __len and __index", 11, 2000,
              setmetatable({}, mt))
  local empty_len = setmetatable({}, {__len = function() return 0 end})
  same("rnd(t) with __len 0", call1(__moy_p8_rnd, empty_len),
       call1(L_rnd, empty_len))
  same("rnd({})", call1(__moy_p8_rnd, {}), call1(L_rnd, {}))
end

-- ---- the bit verbs ------------------------------------------------------
-- PICO-8's are 16.16, fraction included, and the shim's fx/unfx are what put
-- a fractional operand onto the 32-bit image and take it back off. Both lanes
-- run over the same sweep, values and TYPES compared.
local mtype = math.type
local function L_fx(v)
  if mtype(v) == "integer" then return v << 16 end
  local r = v * 65536
  if r >= 2147483648 or r < -2147483648 then
    r = r - 4294967296 * mfloor(r / 4294967296)
    if r >= 2147483648 then r = r - 4294967296 end
  end
  return mfloor(r)
end
local function L_unfx(r)
  if r & 0xffff == 0 then return r // 65536 end
  return r / 65536
end
local function L_is_int(v) return mtype(v) == "integer" end
local function L_band(a, b)
  a, b = a or 0, b or 0
  if L_is_int(a) and L_is_int(b) then return a & b end
  return L_unfx(L_fx(a) & L_fx(b))
end
local function L_bor(a, b)
  a, b = a or 0, b or 0
  if L_is_int(a) and L_is_int(b) then return a | b end
  return L_unfx(L_fx(a) | L_fx(b))
end
local function L_bxor(a, b)
  a, b = a or 0, b or 0
  if L_is_int(a) and L_is_int(b) then return a ~ b end
  return L_unfx(L_fx(a) ~ L_fx(b))
end
local function L_bnot(a)
  a = a or 0
  if L_is_int(a) then return ~a end
  return L_unfx(~L_fx(a))
end
local function L_shl(a, n)
  a, n = a or 0, L_flr(n or 0)
  if L_is_int(a) then return a << n end
  return L_unfx(L_fx(a) << n)
end
local function L_shr(a, n)
  a, n = a or 0, L_flr(n or 0)
  if L_is_int(a) then return a // (1 << n) end
  return L_unfx(L_fx(a) // (1 << n))
end
local function L_lshr(a, n)
  a, n = a or 0, L_flr(n or 0)
  if L_is_int(a) then return (a & 0xffffffff) >> n end
  return L_unfx((L_fx(a) & 0xffffffff) >> n)
end
local function L_rotl(a, n)
  n = L_flr(n or 0) % 32
  local v = L_fx(a or 0) & 0xffffffff
  return L_unfx(((v << n) | (v >> (32 - n))) & 0xffffffff)
end
local function L_rotr(a, n)
  n = L_flr(n or 0) % 32
  local v = L_fx(a or 0) & 0xffffffff
  return L_unfx(((v >> n) | (v << (32 - n))) & 0xffffffff)
end

-- The operands a p8 cart actually reaches these with: whole numbers, packed
-- flag words, parsed decimals, and the coercions on either side of them.
local BITS = {
  0, 1, -1, 2, 7, 255, 256, 65535, 65536, -65536, 0x7fffffff, -0x7fffffff - 1,
  0.5, -0.5, 1.5, -1.5, 0.25, 0.0625, 1/3, 255.99, -255.99,
  32767.5, -32768.0, 1e30, -1e30, 1/0, -1/0, 0/0,
  nil, false, true, "3", "3.5", "abc", {},
}
local NBITS = 35
-- Shift and rotate counts, including the ones that fall off either end.
local COUNTS = {
  0, 1, 4, 15, 16, 31, 32, 33, -1, -16, -32, -33,
  0.5, 1.5, -0.5, 1e30, -1e30, 1/0, 0/0, nil, false, "2", {},
}
local NCOUNTS = 23

function bit_checks()
  check("the bit verbs are the C ones", __moy_band ~= nil and __moy_rotr ~= nil)

  local PAIRS = {
    {"band", __moy_band, L_band}, {"bor", __moy_bor, L_bor},
    {"bxor", __moy_bxor, L_bxor},
  }
  for _, v in ipairs(PAIRS) do
    for i = 1, NBITS do
      for j = 1, NBITS do
        same(v[1] .. "(" .. tostring(BITS[i]) .. ", " .. tostring(BITS[j]) .. ")",
             call1(v[2], BITS[i], BITS[j]), call1(v[3], BITS[i], BITS[j]))
      end
      same(v[1] .. " of one argument", call1(v[2], BITS[i]), call1(v[3], BITS[i]))
    end
  end
  for i = 1, NBITS do
    same("bnot(" .. tostring(BITS[i]) .. ")",
         call1(__moy_bnot, BITS[i]), call1(L_bnot, BITS[i]))
  end
  same("bnot of nothing", call1(__moy_bnot), call1(L_bnot))

  local SHIFTS = {
    {"shl", __moy_shl, L_shl}, {"shr", __moy_shr, L_shr},
    {"lshr", __moy_lshr, L_lshr}, {"rotl", __moy_rotl, L_rotl},
    {"rotr", __moy_rotr, L_rotr},
  }
  for _, v in ipairs(SHIFTS) do
    for i = 1, NBITS do
      for j = 1, NCOUNTS do
        same(v[1] .. "(" .. tostring(BITS[i]) .. ", " .. tostring(COUNTS[j]) .. ")",
             call1(v[2], BITS[i], COUNTS[j]), call1(v[3], BITS[i], COUNTS[j]))
      end
      same(v[1] .. " with no count", call1(v[2], BITS[i]), call1(v[3], BITS[i]))
    end
  end

  -- The idioms the corpus leans on, spelled out so a break says which one.
  check("band(x, -1) is p8's floor", __moy_band(12.75, -1) == 12
        and __moy_band(-12.75, -1) == -13
        and mtype(__moy_band(12.75, -1)) == "integer")
  check("band keeps a fraction", __moy_band(12.75, 0.5) == 0.5)
  check("shr halves", __moy_shr(12.5, 1) == 6.25)
  check("rotl by 0 is identity", __moy_rotl(3.25, 0) == 3.25)
  check("rotl and rotr come back", __moy_rotr(__moy_rotl(0.5, 7), 7) == 0.5)
end

-- ---- the NATIVE bit operators -------------------------------------------
-- A different set from the nine above, sharing only their spelling: these are
-- p8's `a|b`, `a<<b`, `~a` as the PORTER reads them -- flr() on each operand
-- and then Lua's own integer operator. The Lua here is the porter's shim
-- verbatim (p8_lua_port.py, `function __p8_bor(a, b) return flr(a) | flr(b)
-- end`), because a cart reaches whichever lane the host offers and the two
-- must be one answer. The sweep is the same BITS/COUNTS the 16.16 verbs get,
-- so an operand out of int32's range, a nil, a string and a NaN each land on
-- the same side in both lanes -- defined, and defined the same way.
local function LN_bor(a, b) return L_flr(a) | L_flr(b) end
local function LN_band(a, b) return L_flr(a) & L_flr(b) end
local function LN_bxor(a, b) return L_flr(a) ~ L_flr(b) end
local function LN_bnot(a) return ~L_flr(a) end
local function LN_shl(a, b) return L_flr(a) << L_flr(b) end
local function LN_shr(a, b) return L_flr(a) >> L_flr(b) end
local function LN_lshr(a, b) return L_flr(a) >> L_flr(b) end
local function LN_rotl(a, b)
  local v, n = L_flr(a), L_flr(b) % 32
  return (v << n) | (v >> (32 - n))
end
local function LN_rotr(a, b)
  local v, n = L_flr(a), L_flr(b) % 32
  return (v >> n) | (v << (32 - n))
end

function native_bit_checks()
  check("the native bit operators are the C ones",
        __moy_p8_bor ~= nil and __moy_p8_rotr ~= nil)

  local PAIRS = {
    {"__p8_bor", __moy_p8_bor, LN_bor}, {"__p8_band", __moy_p8_band, LN_band},
    {"__p8_bxor", __moy_p8_bxor, LN_bxor},
    {"__p8_shl", __moy_p8_shl, LN_shl}, {"__p8_shr", __moy_p8_shr, LN_shr},
    {"__p8_lshr", __moy_p8_lshr, LN_lshr},
  }
  for _, v in ipairs(PAIRS) do
    for i = 1, NBITS do
      for j = 1, NBITS do
        same(v[1] .. "(" .. tostring(BITS[i]) .. ", " .. tostring(BITS[j]) .. ")",
             call1(v[2], BITS[i], BITS[j]), call1(v[3], BITS[i], BITS[j]))
      end
      -- The shift counts a cart actually writes, which BITS does not carry:
      -- past the width, negative, fractional, and none at all.
      for j = 1, NCOUNTS do
        same(v[1] .. "(" .. tostring(BITS[i]) .. ", " .. tostring(COUNTS[j]) .. ")",
             call1(v[2], BITS[i], COUNTS[j]), call1(v[3], BITS[i], COUNTS[j]))
      end
      same(v[1] .. " of one argument", call1(v[2], BITS[i]), call1(v[3], BITS[i]))
    end
    same(v[1] .. " of nothing at all", call1(v[2]), call1(v[3]))
  end

  for i = 1, NBITS do
    same("__p8_bnot(" .. tostring(BITS[i]) .. ")",
         call1(__moy_p8_bnot, BITS[i]), call1(LN_bnot, BITS[i]))
  end
  same("__p8_bnot of nothing", call1(__moy_p8_bnot), call1(LN_bnot))

  local ROTS = {
    {"__p8_rotl", __moy_p8_rotl, LN_rotl}, {"__p8_rotr", __moy_p8_rotr, LN_rotr},
  }
  for _, v in ipairs(ROTS) do
    for i = 1, NBITS do
      for j = 1, NCOUNTS do
        same(v[1] .. "(" .. tostring(BITS[i]) .. ", " .. tostring(COUNTS[j]) .. ")",
             call1(v[2], BITS[i], COUNTS[j]), call1(v[3], BITS[i], COUNTS[j]))
      end
      same(v[1] .. " with no count", call1(v[2], BITS[i]), call1(v[3], BITS[i]))
    end
  end

  -- What the porter's reading MEANS, spelled out so a break says which part.
  -- These are the answers the emitted `flr(a) | flr(b)` gave, and the reason
  -- they are not the 16.16 verbs' answers.
  check("a fraction is floored away, not carried",
        __moy_p8_band(12.75, 0.5) == 0 and __moy_band(12.75, 0.5) == 0.5)
  check("the answer is always an integer",
        math.type(__moy_p8_bor(1.5, 2.5)) == "integer")
  check("a negative operand floors DOWN", __moy_p8_band(-12.75, -1) == -13)
  check("nil is zero, as `flr(v or 0)` is",
        __moy_p8_bor(nil, 5) == 5 and __moy_p8_band(7) == 0)
  check("`>>` is p8's `>>>`: logical, so a negative goes positive",
        __moy_p8_shr(-1, 1) == 0x7fffffff
        and __moy_p8_lshr(-1, 1) == __moy_p8_shr(-1, 1))
  check("a count past the width is zero, not undefined",
        __moy_p8_shl(1, 32) == 0 and __moy_p8_shr(-1, 99) == 0)
  check("a rotate comes back round",
        __moy_p8_rotr(__moy_p8_rotl(0x1234, 9), 9) == 0x1234
        and __moy_p8_rotl(1, 31) == -2147483648)
  check("an operand past int32 raises rather than wrapping",
        not pcall(__moy_p8_band, 1e30, 1) and not pcall(LN_band, 1e30, 1))
end

-- ---- the map and flag verbs ---------------------------------------------
-- mget/mset walk the machine's map memory; fget/fset the console's flag
-- table, which the machine keeps in step with 0x3000.
local m_fget, m_fset = fget, fset

local function L_maddr(x, y)
  if y < 32 then return 0x2000 + y * 128 + x end
  return 0x1000 + (y - 32) * 128 + x
end
local function L_mget(x, y)
  x, y = mfloor(x or 0), mfloor(y or 0)
  if x < 0 or x > 127 or y < 0 or y > 63 then return 0 end
  return cpeek(L_maddr(x, y))
end
local function L_mset(x, y, v)
  x, y = mfloor(x or 0), mfloor(y or 0)
  if x < 0 or x > 127 or y < 0 or y > 63 then return end
  cpoke(L_maddr(x, y), v or 0)
end
local function L_fget(n, f)
  n = L_fl(n)
  if f == nil then return m_fget(n) end
  return m_fget(n, L_fl(f))
end
local function L_fset(n, f, v)
  n = L_fl(n)
  if v == nil then m_fset(n, L_fl(f)) else m_fset(n, L_fl(f), v and true or false) end
end

local COORDS = {
  0, 1, 5, 31, 32, 33, 63, 64, 127, 128, -1, -128,
  0.5, -0.5, 127.9, 63.9, 1e30, -1e30, 0/0, nil, false, "5", "abc", {},
}
local NCOORDS = 24

function map_checks()
  check("the map verbs are the C ones", __moy_mget ~= nil and __moy_fget ~= nil)

  -- a pattern the whole map region can be read back from
  for a = 0x1000, 0x2fff, 1 do cpoke(a, (a * 31) & 0xff) end
  for i = 1, NCOORDS do
    for j = 1, NCOORDS do
      same("mget(" .. tostring(COORDS[i]) .. ", " .. tostring(COORDS[j]) .. ")",
           call1(__moy_mget, COORDS[i], COORDS[j]),
           call1(L_mget, COORDS[i], COORDS[j]))
    end
    same("mget of one coordinate", call1(__moy_mget, COORDS[i]), call1(L_mget, COORDS[i]))
  end

  -- mset: the same case list through each lane, then the whole region digested
  local function mset_lane(f)
    for a = 0x1000, 0x2fff do cpoke(a, (a * 31) & 0xff) end
    for i = 1, NCOORDS do
      for j = 1, NCOORDS do
        pcall(f, COORDS[i], COORDS[j], (i * 7 + j) & 0xff)
      end
      pcall(f, COORDS[i], 3)                       -- no value: p8 writes 0
    end
    local h = 0
    for a = 0x1000, 0x2fff do h = (h * 31 + cpeek(a)) & 0x7fffffff end
    return h
  end
  same("mset writes the same bytes", mset_lane(__moy_mset), mset_lane(L_mset))

  -- fget / fset
  for a = 0, 255 do m_fset(a, (a * 13) & 0xff) end
  for i = 1, NCOORDS do
    for j = 1, NCOORDS do
      same("fget(" .. tostring(COORDS[i]) .. ", " .. tostring(COORDS[j]) .. ")",
           call1(__moy_fget, COORDS[i], COORDS[j]),
           call1(L_fget, COORDS[i], COORDS[j]))
    end
    same("fget of one", call1(__moy_fget, COORDS[i]), call1(L_fget, COORDS[i]))
  end

  local function fset_lane(f)
    for a = 0, 255 do m_fset(a, (a * 13) & 0xff) end
    for i = 1, NCOORDS do
      for j = 1, NCOORDS do
        pcall(f, COORDS[i], COORDS[j])                    -- the byte form
        pcall(f, COORDS[i], COORDS[j], (i + j) % 2 == 0)  -- the bit form
        pcall(f, COORDS[i], COORDS[j], nil)               -- an explicit nil
      end
    end
    local h = 0
    for a = 0, 255 do h = (h * 31 + m_fget(a)) & 0x7fffffff end
    return h
  end
  same("fset writes the same flags", fset_lane(__moy_fset), fset_lane(L_fset))

  -- the flags are the memory map's, both ways
  __moy_fset(9, 0x81)
  check("fset shows at 0x3000", cpeek(0x3009) == 0x81)
  cpoke(0x300a, 0x42)
  check("a poke at 0x3000 shows in fget", __moy_fget(10) == 0x42
        and __moy_fget(10, 6) == true and __moy_fget(10, 0) == false)
  -- and the shared rows really are shared
  __moy_mset(3, 40, 0x5c)
  check("map rows 32-63 live under the sheet", cpeek(0x1000 + 8 * 128 + 3) == 0x5c)
end

-- ---- the lookup-table span ----------------------------------------------
-- `__moy_lut_span(from, to, lut)` is the C for the ONE statement the porter
-- folds (p8_lua_port.fold_lut_span): `for a=i,j do poke(a,peek(lut|peek(a)))
-- end`, a run of memory pushed through a table. The shim's Lua body for that
-- call is the cart's own loop, so it is the reference here too -- and the
-- addresses that matter are the ones with a console object behind them: the
-- SCREEN (which reads and writes the canvas, not the array), the sheet, and
-- the wrap past 0xffff.
local function L_lut_span(from, to, lut)
  for a = from, to do cpoke(a, cpeek(mfloor(lut) | mfloor(cpeek(a)))) end
end

local SPAN_SEED = {
  {0x0000, 0x00ff}, {0x2000, 0x20ff}, {0x4300, 0x44ff},
  {0x5f00, 0x5fff}, {0x6000, 0x60ff}, {0x7f00, 0x7fff}, {0xff00, 0xffff},
}

local function span_seed()
  for _, r in ipairs(SPAN_SEED) do
    for a = r[1], r[2] do cpoke(a, (a * 37 + (a >> 8)) & 0xff) end
  end
end

local function span_digest()
  local h = 0
  for _, r in ipairs(SPAN_SEED) do
    for a = r[1], r[2] do h = (h * 31 + cpeek(a)) & 0x7fffffff end
  end
  return h
end

-- from, to, lut. The C takes three plain integers and declines everything
-- else, so both kinds are here: the ones it runs and the ones it hands back.
local SPANS = {
  {0x4400, 0x441f, 0x4300},
  {0x4400, 0x4400, 0x4300},
  {0x4400, 0x43ff, 0x4300},           -- empty: from > to
  {0x5ff0, 0x6041, 0x4300},           -- into the screen window
  {0x6000, 0x60ff, 0x4300},           -- the canvas, and only the canvas
  {0x7fc0, 0x8001, 0x4300},           -- out the far side of it
  {0xfffe, 0x10001, 0x4300},          -- past the top: the address wrap
  {-2, 1, 0x4300},                    -- a negative address, into the sheet
  {0x4400, 0x441f, -1},               -- lut | v below 0
  {0x4400, 0x441f, 0x1ff00},          -- lut | v past 0xffff
  {0x4400, 0x441f, 0},
  {0x2000, 0x20ff, 0x4300},           -- the map, mirrored to the console's
}

local DECLINED = {
  {0x4400.5, 0x441f, 0x4300}, {0x4400, 0x441f.5, 0x4300},
  {0x4400, 0x441f, 0x4300.5}, {0x4400, 0x441f}, {},
  {"17408", 0x441f, 0x4300}, {0x4400, 0x441f, "17152"},
  {0x4400, 0x441f, true}, {0/0, 0x441f, 0x4300},
}

function span_checks()
  check("the lut span is the C one", __moy_lut_span ~= nil)

  for k, c in ipairs(SPANS) do
    span_seed()
    check("lut span case " .. k .. " ran in C",
          __moy_lut_span(c[1], c[2], c[3]) == true)
    local c_side = span_digest()
    span_seed()
    L_lut_span(c[1], c[2], c[3])
    same("lut span case " .. k, c_side, span_digest())
  end

  -- Anything but three plain integers is DECLINED: false, and not a byte
  -- written, so the shim falls back to the loop with the state untouched.
  for k, c in ipairs(DECLINED) do
    span_seed()
    local fresh = span_digest()
    check("lut span declines case " .. k,
          __moy_lut_span(c[1], c[2], c[3]) == false)
    same("a declined lut span writes nothing (case " .. k .. ")",
         span_digest(), fresh)
  end

  -- The canvas really is the screen: a span over 0x6000 is what pix() reads.
  cls(0)
  pix(0, 0, 12)
  for a = 0x4300, 0x43ff do cpoke(a, 7) end        -- every lookup answers 7
  __moy_lut_span(0x6000, 0x6000, 0x4300)
  check("a lut span over the screen writes the canvas", cpeek(0x6000) == 7)
end

-- ---- the span as the WHOLE verb -----------------------------------------
-- __moy_p8_lut_span(fallback) hands back __p8_lut_span itself, keeping the
-- shim's loop for the cases it declines. That makes the pin STRICTLY stronger
-- than the one above: the boolean verb only had to be right about the cases
-- it accepted, and this one owns the declines too. So every case -- accepted
-- and declined alike -- has to leave the same memory as the loop AND raise
-- the same way, and the declined ones have to actually reach the fallback
-- rather than being quietly dropped.
function span_verb_checks()
  check("the whole-verb lut span is bindable", __moy_p8_lut_span ~= nil)
  local calls = 0
  local verb = __moy_p8_lut_span(function(from, to, lut)
    calls = calls + 1
    L_lut_span(from, to, lut)
  end)
  check("the factory answers a function", type(verb) == "function")

  local function lane(fn, c)
    span_seed()
    local ok = pcall(fn, c[1], c[2], c[3])
    return ok, span_digest()
  end

  for k, c in ipairs(SPANS) do
    calls = 0
    local c_ok, c_hash = lane(verb, c)
    local reached = calls
    local l_ok, l_hash = lane(L_lut_span, c)
    same("verb span case " .. k .. " raised alike", c_ok, l_ok)
    same("verb span case " .. k, c_hash, l_hash)
    check("verb span case " .. k .. " stayed in C", reached == 0)
  end

  for k, c in ipairs(DECLINED) do
    calls = 0
    local c_ok, c_hash = lane(verb, c)
    local reached = calls
    local l_ok, l_hash = lane(L_lut_span, c)
    same("declined verb case " .. k .. " raised alike", c_ok, l_ok)
    same("declined verb case " .. k, c_hash, l_hash)
    check("declined verb case " .. k .. " reached the fallback", reached == 1)
  end

  -- THE ARITY IS PART OF THE INPUT (split's lesson, and the same defence):
  -- the fallback reads three, so it is handed three whatever the cart passed.
  local seen
  local counting = __moy_p8_lut_span(function(...) seen = select("#", ...) end)
  counting(0x4400.5, 0x441f, 0x4300, 99)
  same("a fourth argument does not ride along", seen, 3)
  counting(0x4400.5)
  same("a one-argument call still arrives as three", seen, 3)
end

-- ---- the glyph rasteriser -----------------------------------------------
-- A GOLDEN, like conformance's: nine renders through the PICO-8 font, hashed.
-- The outline is computed a row at a time now (moy_p8.c), and row arithmetic
-- is the kind of thing that stays plausible while being one pixel out, so the
-- geometry is pinned rather than argued about. Every mode that changes it is
-- here: plain, an outline in a colour, "$" and "!", wide and tall together,
-- inverted over a background, the 7-wide P8SCII glyphs and the button codes,
-- and two renders straddling a canvas edge. Regenerate only for a deliberate
-- change to the font or the rasteriser, and say which in the commit.
local FONT_PINS = {
  {"Ag", 20, 30, 7, 1708227433},
  {E6 .. "o701Ag", 20, 30, 7, 929240231},
  {E6 .. "o$ffAg", 20, 30, 9, 1913957642},
  {E6 .. "o!ffAg", 20, 30, 9, 638015363},
  {E6 .. "w" .. E6 .. "t" .. E6 .. "o3a5Ag", 20, 30, 12, 113299532},
  {E6 .. "i" .. E2 .. "5Ag", 20, 30, 12, 83277239},
  {E6 .. "w" .. string.char(135) .. string.char(151) .. "z", 4, 4, 11, 238837998},
  {E6 .. "o0ffWq", -3, -2, 8, 1109368336},
  {E6 .. "t" .. E6 .. "o20fMj", 118, 118, 14, 1014451440},
}

function font_checks()
  for i, c in ipairs(FONT_PINS) do
    cls(0)
    __moy_p8print(c[1], c[2], c[3], c[4])
    local h = 0
    for a = 0x6000, 0x7fff do h = (h * 33 + cpeek(a)) & 0x7fffffff end
    same("glyph render " .. i, h, c[5])
  end
  cls(0)
end


-- ---- the draw verbs -----------------------------------------------------
-- Every p8 draw verb the machine now carries (moy_p8.c), held against the
-- SHIM'S OWN LUA -- the wrapper in p8_lua_port.py, transcribed below and
-- calling the same console verbs it calls there. A cart may reach either
-- lane, so the two must answer alike: the same pixels, the same draw state,
-- the same return value.
--
-- Every case runs TWICE from the same reset -- once per lane -- and the whole
-- screen is digested after each, along with the draw state the verb is
-- allowed to move (palette, transparency, clip, camera) and the pen and
-- cursor, which live in the machine's memory on one side and in a local on
-- the other. The states are swept ACROSS the ops rather than beside them,
-- because that is where the bugs are: a dropped floor shows up only at a
-- fractional coordinate, a skipped palette map only with a palette set, a
-- lost camera only with a camera.
local m_pix, m_line = pix, line
local m_rect, m_rectb = rect, rectb
local m_circ, m_circb = circ, circb
local m_oval, m_ovalb = oval, ovalb
local m_spr, m_sspr, m_map = spr, sspr, map
local m_pal, m_palt, m_fillp = pal, palt, fillp
local m_camera, m_clip, m_cls = camera, clip, cls
local m_p8print = __moy_p8print
local mtype_ = math.type

local L_pen, L_cx, L_cy = 6, 0, 0
local L_pat, L_transp = 0, false
local L_camx, L_camy = 0, 0
local L_spal = {}

local function L_pcol(c) return L_fl(c == nil and L_pen or c) & 15 end
local function L_scol(c)
  c = L_fl(c or 0)
  if c >= 128 then return 16 + (c & 15) end
  return c & 15
end
local function L_shape_col(c)
  c = L_fl(c == nil and L_pen or c)
  if L_pat ~= 0 then m_fillp(L_pat, L_transp and -1 or ((c >> 4) & 15)) end
  return c & 15
end
local function L_fill_skip() return L_transp and L_pat == 0xffff end

local function L_pset(x, y, c) m_pix(L_fl(x), L_fl(y), L_pcol(c)) end
local function L_pget(x, y) return m_pix(L_fl(x), L_fl(y)) end

local function L_line(x0, y0, x1, y1, c)
  if L_fill_skip() then return end
  m_line(L_fl(x0), L_fl(y0), L_fl(x1), L_fl(y1), L_shape_col(c))
end

local function L_rectfill(x0, y0, x1, y1, c)
  if L_fill_skip() then return end
  x0 = L_fl(x0) y0 = L_fl(y0) x1 = L_fl(x1) y1 = L_fl(y1)
  if x1 < x0 then x0, x1 = x1, x0 end
  if y1 < y0 then y0, y1 = y1, y0 end
  m_rect(x0, y0, x1 - x0 + 1, y1 - y0 + 1, L_shape_col(c))
end

local function L_rect(x0, y0, x1, y1, c)
  if L_fill_skip() then return end
  x0 = L_fl(x0) y0 = L_fl(y0) x1 = L_fl(x1) y1 = L_fl(y1)
  if x1 < x0 then x0, x1 = x1, x0 end
  if y1 < y0 then y0, y1 = y1, y0 end
  m_rectb(x0, y0, x1 - x0 + 1, y1 - y0 + 1, L_shape_col(c))
end

local function L_circfill(x, y, r, c)
  if L_fill_skip() then return end
  m_circ(L_fl(x), L_fl(y), L_fl(r), L_shape_col(c))
end

local function L_circ(x, y, r, c)
  if L_fill_skip() then return end
  m_circb(L_fl(x), L_fl(y), L_fl(r), L_shape_col(c))
end

local function L_oval_box(x0, y0, x1, y1)
  x0, y0, x1, y1 = L_fl(x0), L_fl(y0), L_fl(x1), L_fl(y1)
  if x1 < x0 then x0, x1 = x1, x0 end
  if y1 < y0 then y0, y1 = y1, y0 end
  return x0, y0, x1 - x0 + 1, y1 - y0 + 1
end

local function L_oval(x0, y0, x1, y1, col)
  if L_fill_skip() then return end
  local x, y, w, h = L_oval_box(x0, y0, x1, y1)
  m_ovalb(x, y, w, h, L_shape_col(col))
end

local function L_ovalfill(x0, y0, x1, y1, col)
  if L_fill_skip() then return end
  local x, y, w, h = L_oval_box(x0, y0, x1, y1)
  m_oval(x, y, w, h, L_shape_col(col))
end

local function L_spr(n, x, y, w, h, fx, fy)
  local flip = (fx and 1 or 0) + (fy and 2 or 0)
  n = L_fl(n)
  x = L_fl(x)
  y = L_fl(y)
  w = w or 1
  h = h or 1
  if w == 1 and h == 1 then
    m_spr(n, x, y, -1, 1, flip)
  else
    for ty = 0, h - 1 do
      for tx = 0, w - 1 do
        local cx = fx and (w - 1 - tx) or tx
        local cy = fy and (h - 1 - ty) or ty
        m_spr(n + cx + cy * 16, x + tx * 8, y + ty * 8, -1, 1, flip)
      end
    end
  end
end

local function L_sspr(sx, sy, sw, sh, dx, dy, dw, dh, fx, fy)
  local f = 0
  if fx then f = f + 1 end
  if fy then f = f + 2 end
  m_sspr(sx, sy, sw, sh, dx, dy, dw or sw, dh or sh, -1, f)
end

local function L_camera(cx, cy)
  L_camx, L_camy = L_fl(cx), L_fl(cy)
  m_camera(L_camx, L_camy)
end

local function L_map(celx, cely, sx, sy, cw, ch, mask)
  celx = mfloor(celx or 0)
  cely = mfloor(cely or 0)
  sx = mfloor(sx or 0)
  sy = mfloor(sy or 0)
  cw = mfloor(cw or 128)
  ch = mfloor(ch or 64)
  mask = mask or 0
  local i0 = (L_camx - sx) // 8
  local i1 = (L_camx + 127 - sx) // 8
  if i0 > 0 then celx, sx, cw = celx + i0, sx + i0 * 8, cw - i0 i1 = i1 - i0 end
  if i1 + 1 < cw then cw = i1 + 1 end
  local j0 = (L_camy - sy) // 8
  local j1 = (L_camy + 127 - sy) // 8
  if j0 > 0 then cely, sy, ch = cely + j0, sy + j0 * 8, ch - j0 j1 = j1 - j0 end
  if j1 + 1 < ch then ch = j1 + 1 end
  if cw <= 0 or ch <= 0 then return end
  m_map(celx, cely, cw, ch, sx, sy, -1, 1, mask)
end

local function L_p8str(v)
  if mtype_(v) == "float" and v == mfloor(v) and v > -2147483648 and v < 2147483648 then
    return tostring(mfloor(v))
  end
  return tostring(v)
end

local function L_print(s, x, y, c)
  s = L_p8str(s)
  if y == nil then
    c = x
    x, y = L_cx, L_cy
    L_cy = L_cy + 6
  end
  c = L_pcol(c)
  local lx = L_fl(x)
  return m_p8print(s, lx, L_fl(y), c)
end

local function L_palt_default() m_palt() m_palt(0, true) end
local function L_spal_set(c0, c1) L_spal[c0] = c1 m_pal(c0, c1, 1) end

local function L_pal(a, b, p)
  if a == nil then m_pal() L_spal = {} L_palt_default() return end
  if type(a) == "table" then
    local screen = (b == 1)
    for k, v in pairs(a) do
      if type(k) == "number" and type(v) == "number" then
        if screen then L_spal_set(L_fl(k) & 15, L_scol(v))
        else m_pal(L_fl(k) & 15, L_pcol(v)) end
      end
    end
    return
  end
  if p == 1 then L_spal_set(L_fl(a) & 15, L_scol(b)) return end
  m_pal(L_fl(a) & 15, L_pcol(b))
end

local function L_palt(c, t)
  if c == nil then L_palt_default() return end
  if t == nil then
    local bits = L_fl(c)
    m_palt()
    for i = 0, 15 do m_palt(i, (bits >> (15 - i)) & 1 == 1) end
    return
  end
  m_palt(L_fl(c) & 15, t and true or false)
end

local function L_fillp(p)
  p = p or 0
  if type(p) ~= "number" then p = tonumber(p) or 0 end
  L_pat = mfloor(p) & 0xffff
  L_transp = (p % 1) >= 0.5
  if L_pat == 0 then m_fillp() end
end

local function L_color(c) L_pen = L_fl(c or 6) & 0x8f end
local function L_cursor(x, y, c)
  L_cx, L_cy = L_fl(x or 0), L_fl(y or 0)
  if c ~= nil then L_pen = L_fl(c) & 0x8f end
end

local function L_sget(x, y)
  x, y = L_fl(x), L_fl(y)
  if x < 0 or x > 127 or y < 0 or y > 127 then return 0 end
  local b = cpeek(y * 64 + (x >> 1))
  if x & 1 == 1 then return b >> 4 end
  return b & 15
end

local function L_sset(x, y, c)
  x, y = L_fl(x), L_fl(y)
  if x < 0 or x > 127 or y < 0 or y > 127 then return end
  c = L_fl(c or 6) % 16
  local a = y * 64 + (x >> 1)
  local b = cpeek(a)
  if x & 1 == 1 then cpoke(a, (b & 0x0f) | (c << 4))
  else cpoke(a, (b & 0xf0) | c) end
end

-- ---- the two lanes ------------------------------------------------------
local LANE_C = {
  name = "C",
  pset = __moy_p8_pset, pget = __moy_p8_pget, line = __moy_p8_line,
  rect = __moy_p8_rect, rectfill = __moy_p8_rectfill,
  circ = __moy_p8_circ, circfill = __moy_p8_circfill,
  oval = __moy_p8_oval, ovalfill = __moy_p8_ovalfill,
  spr = __moy_p8_spr, sspr = __moy_p8_sspr, map = __moy_p8_map,
  print = __moy_p8_print, pal = __moy_p8_pal, palt = __moy_p8_palt,
  fillp = __moy_p8_fillp, color = __moy_p8_color, cursor = __moy_p8_cursor,
  camera = __moy_p8_camera, sget = __moy_p8_sget, sset = __moy_p8_sset,
  -- the pen and the cursor, from where this lane keeps them
  pen = function() return cpeek(0x5f25) end,
  cur = function() return cpeek(0x5f26) .. "," .. cpeek(0x5f27) end,
}
local LANE_L = {
  name = "Lua",
  pset = L_pset, pget = L_pget, line = L_line,
  rect = L_rect, rectfill = L_rectfill,
  circ = L_circ, circfill = L_circfill,
  oval = L_oval, ovalfill = L_ovalfill,
  spr = L_spr, sspr = L_sspr, map = L_map,
  print = L_print, pal = L_pal, palt = L_palt,
  fillp = L_fillp, color = L_color, cursor = L_cursor,
  camera = L_camera, sget = L_sget, sset = L_sset,
  pen = function() return L_pen & 0xff end,
  cur = function() return (L_cx & 0xff) .. "," .. (L_cy & 0xff) end,
}

-- Both lanes draw on ONE canvas, so every case starts from the same reset:
-- the console's draw state, the machine's bytes, and the Lua lane's locals.
local function reset_draw()
  m_clip() m_camera() m_fillp() m_pal() m_palt() m_palt(0, true)
  for i = 0, 15 do cpoke(0x5f10 + i, i) end
  cpoke(0x5f25, 6) cpoke(0x5f26, 0) cpoke(0x5f27, 0)
  cpoke(0x5f31, 0) cpoke(0x5f32, 0) cpoke(0x5f33, 0)
  L_pen, L_cx, L_cy = 6, 0, 0
  L_pat, L_transp = 0, false
  L_camx, L_camy = 0, 0
  L_spal = {}
end

-- The screen, then the draw state a verb may move. 0x5f24-0x5f27 and
-- 0x5f31-0x5f33 are LEFT OUT on purpose: those are the machine's own bytes
-- and the Lua lane has no equivalent to peek -- they are compared through the
-- lane's pen()/cur() instead.
local function draw_digest(sheet)
  local h = 0
  for a = 0x6000, 0x7fff do h = (h * 31 + cpeek(a)) & 0x7fffffff end
  for a = 0x5f00, 0x5f23 do h = (h * 31 + cpeek(a)) & 0x7fffffff end
  for a = 0x5f28, 0x5f2b do h = (h * 31 + cpeek(a)) & 0x7fffffff end
  if sheet then
    for a = 0x0000, 0x1fff do h = (h * 31 + cpeek(a)) & 0x7fffffff end
  end
  return h
end

local STATES = {
  {"plain", function() end},
  {"pen 9", function(V) V.color(9) end},
  {"pen 0x83", function(V) V.color(0x83) end},
  {"draw palette", function(V) V.pal(1, 7) V.pal(3, 11) V.pal(12, 2) end},
  {"palette table", function(V) V.pal({[0] = 5, [1] = 6, [7] = 8}) end},
  {"transparency", function(V) V.palt(0, false) V.palt(11, true) end},
  {"palt bitfield", function(V) V.palt(0x8421) end},
  {"screen palette", function(V) V.pal(2, 0x8c, 1) V.pal(4, 9, 1) end},
  {"fillp", function(V) V.fillp(0x5a5a) end},
  {"fillp transparent", function(V) V.fillp(0x5a5a + 0.5) end},
  {"fillp all transparent", function(V) V.fillp(0xffff + 0.5) end},
  {"camera", function(V) V.camera(-7, 13) end},
  -- A camera far enough left and up that a NEGATIVE coordinate lands on
  -- screen, which is the only place a floor and a truncation part company.
  {"camera off the origin", function(V) V.camera(-40, -30) end},
  {"clip", function() m_clip(10, 12, 60, 40) end},
  {"cursor", function(V) V.cursor(11.5, 60.5) end},
  {"all at once", function(V)
    V.camera(5.5, -9.5) m_clip(3, 4, 100, 90) V.fillp(0x33cc)
    V.color(0x2b) V.pal(2, 14) V.palt(3, true) V.cursor(9, 40)
  end},
}

-- name, body, and whether the SHEET has to be digested too (sset writes it).
local OPS = {
  {"pset", function(V) V.pset(3.7, 5.2, 9) end},
  {"pset with no colour", function(V) V.pset(9, 5) end},
  {"pset negative", function(V) V.pset(-2.5, -1.5, 12) end},
  {"pset off screen", function(V) V.pset(200, 200, 3) end},
  {"pset a numeric string", function(V) V.pset(4, 6, "5") end},
  {"pset a bad colour", function(V) V.pset(5, 7, true) end},
  {"pset colour 0x83", function(V) V.pset(6, 8, 0x83) end},
  -- A colour byte is FOUR bits at the draw end, so 0x27 is 7 and not 39 --
  -- 39 is a real palette index here and would have drawn.
  {"pset colour 0x27", function(V) V.pset(7, 9, 0x27) end},
  {"pset with no arguments", function(V) V.pset() end},
  {"pget", function(V) V.pset(10, 11, 12) return V.pget(10.9, 11.9) end},
  {"pget off screen", function(V) return V.pget(-3, 400) end},
  {"line", function(V) V.line(1.5, 2.5, 30.7, 40.2, 8) end},
  {"line backwards", function(V) V.line(30, 40, 1, 2) end},
  {"line negative", function(V) V.line(-5.5, -5.5, 20, 20, 3) end},
  {"line horizontal", function(V) V.line(2, 9, 60, 9, 14) end},
  {"line negative fractional", function(V) V.line(-5.5, -9.5, 20, 20, 3) end},
  {"line one pixel", function(V) V.line(9, 9, 9, 9, 14) end},
  {"line with no arguments", function(V) V.line() end},
  {"rectfill", function(V) V.rectfill(10.5, 12.5, 40.2, 30.9, 7) end},
  {"rectfill reversed", function(V) V.rectfill(40, 30, 10, 12, 0x27) end},
  {"rectfill with no colour", function(V) V.rectfill(2, 2, 20, 20) end},
  {"rectfill negative", function(V) V.rectfill(-6.5, -4.5, 5, 6, 3) end},
  {"rectfill whole screen", function(V) V.rectfill(0, 0, 127, 127, 0x51) end},
  {"rect", function(V) V.rect(10.5, 12.5, 40.2, 30.9, 7) end},
  {"rect reversed", function(V) V.rect(40, 30, 10, 12, 0x27) end},
  {"rect one pixel", function(V) V.rect(5, 5, 5, 5) end},
  {"circfill", function(V) V.circfill(30.5, 30.5, 12.9, 11) end},
  {"circfill r=0", function(V) V.circfill(20, 20, 0, 3) end},
  {"circfill r=-1", function(V) V.circfill(20, 20, -1, 3) end},
  {"circfill oversized", function(V) V.circfill(64, 64, 80, 0x35) end},
  {"circfill negative", function(V) V.circfill(-2.5, -2.5, 20, 3) end},
  {"circ", function(V) V.circ(30.5, 30.5, 12.9, 11) end},
  {"circ with no colour", function(V) V.circ(40, 40, 7) end},
  {"ovalfill", function(V) V.ovalfill(5.5, 6.5, 60.2, 30.7, 4) end},
  {"ovalfill reversed", function(V) V.ovalfill(60, 30, 5, 6, 0x14) end},
  {"oval", function(V) V.oval(5.5, 6.5, 60.2, 30.7, 4) end},
  {"oval flat", function(V) V.oval(10, 10, 40, 10) end},
  {"ovalfill negative", function(V) V.ovalfill(-3.5, -2.5, 30, 20, 4) end},
  {"spr", function(V) V.spr(1, 3.5, 4.5) end},
  {"spr negative", function(V) V.spr(1, -2.5, -1.5) end},
  {"spr 2x2", function(V) V.spr(1, 10, 12, 2, 2) end},
  {"spr 2x2 flipped both ways", function(V) V.spr(1, 10, 12, 2, 2, true, true) end},
  {"spr 3x1 flipped in x", function(V) V.spr(17, 20.5, 30.5, 3, 1, true, false) end},
  {"spr with a fractional size", function(V) V.spr(2, 8, 8, 2.5, 1.5) end},
  {"spr with no arguments", function(V) V.spr() end},
  {"spr off the sheet", function(V) V.spr(600, 5, 5) end},
  {"sspr", function(V) V.sspr(0, 0, 8, 8, 10, 10) end},
  {"sspr scaled", function(V) V.sspr(8, 8, 8, 8, 10.5, 10.5, 24, 24) end},
  {"sspr flipped", function(V) V.sspr(0, 0, 16, 8, 4, 40, 32, 16, true, true) end},
  {"sspr negative", function(V) V.sspr(0, 0, 8, 8, -4, -4, 20, 20) end},
  {"map", function(V) V.map() end},
  {"map a window", function(V) V.map(2, 3, 8.5, 9.5, 6, 5) end},
  {"map masked", function(V) V.map(0, 0, 0, 0, 16, 16, 1) end},
  {"map off the left", function(V) V.map(0, 0, -13, -5, 4, 4) end},
  {"print", function(V) return V.print("Ag!", 3.5, 4.5, 9) end},
  {"print with no colour", function(V) return V.print("Ag!", 3, 4) end},
  {"print negative", function(V) return V.print("Ag!", -2.5, -1.5, 9) end},
  {"print at the cursor", function(V)
     local a = V.print("one") return a .. "," .. V.print("two") end},
  {"print at the cursor with a colour", function(V) return V.print("hi", 9) end},
  {"print an integral float", function(V) return V.print(12.0, 3, 4, 7) end},
  {"print a fraction", function(V) return V.print(1.5, 3, 4, 7) end},
  {"print a boolean", function(V) return V.print(true, 3, 4, 7) end},
  {"print colour 0x27", function(V) return V.print("Ag!", 3, 4, 0x27) end},
  {"print P8SCII", function(V) return V.print(E6 .. "wA" .. E6 .. "tB", 2, 2, 8) end},
  {"color", function(V) V.color(9) V.pset(3, 3) end},
  {"color with no argument", function(V) V.color() V.pset(3, 3) end},
  {"color 0x83", function(V) V.color(0x83) V.rectfill(1, 1, 4, 4) end},
  {"color fractional", function(V) V.color(3.9) V.pset(3, 3) end},
  {"cursor", function(V) V.cursor(20.5, 30.5) return V.print("x") end},
  {"cursor with a colour", function(V) V.cursor(2, 3, 12) return V.print("x") end},
  {"cursor with no arguments", function(V) V.cursor() return V.print("x") end},
  {"pal one entry", function(V) V.pal(1, 7) V.rectfill(0, 0, 8, 8, 1) end},
  {"pal to the secret sixteen", function(V) V.pal(1, 0x87) V.rectfill(0, 0, 8, 8, 1) end},
  {"pal screen", function(V) V.pal(1, 0x87, 1) V.rectfill(0, 0, 8, 8, 1) end},
  {"pal a table", function(V) V.pal({[0] = 3, [1] = 4, [7] = 2}) V.rectfill(0, 0, 8, 8, 1) end},
  {"pal an array", function(V) V.pal({7, 6, 5}) V.rectfill(0, 0, 8, 8, 1) end},
  {"pal a table onto the screen", function(V) V.pal({[1] = 2, [2] = 3}, 1) V.rectfill(0, 0, 8, 8, 1) end},
  {"pal reset", function(V) V.pal() V.spr(1, 0, 0) end},
  {"palt one", function(V) V.palt(0, false) V.spr(1, 0, 0) end},
  {"palt a bitfield", function(V) V.palt(0x8421) V.spr(1, 0, 0) end},
  {"palt reset", function(V) V.palt() V.spr(1, 0, 0) end},
  {"fillp on", function(V) V.fillp(0x5a5a) V.rectfill(0, 0, 30, 30, 0x74) end},
  {"fillp transparent", function(V) V.fillp(0x5a5a + 0.5) V.circfill(20, 20, 15, 9) end},
  {"fillp off", function(V) V.fillp(0) V.rectfill(0, 0, 30, 30, 0x74) end},
  {"fillp a numeric string", function(V) V.fillp("23130") V.rectfill(0, 0, 30, 30, 3) end},
  {"fillp a negative fraction", function(V) V.fillp(-0.5) V.rectfill(0, 0, 30, 30, 3) end},
  {"fillp then a sprite", function(V) V.fillp(0x5a5a) V.spr(1, 4, 4) end},
  {"camera", function(V) V.camera(10.5, -3.5) V.rectfill(0, 0, 40, 40, 6) end},
  {"camera reset", function(V) V.camera() V.rectfill(0, 0, 40, 40, 6) end},
  {"sget", function(V)
     return V.sget(3.5, 4.5) .. "," .. V.sget(4, 4) .. "," ..
            V.sget(-1, 0) .. "," .. V.sget(200, 3) end},
  {"sset", function(V)
     V.sset(3.5, 4.5, 9) V.sset(4, 4) V.sset(5, 4, -1) V.sset(200, 3, 1)
     V.spr(0, 0, 0) end, true},
}

function draw_checks()
  check("the draw verbs are the C ones",
        __moy_p8_pset ~= nil and __moy_p8_map ~= nil and __moy_p8_fillp ~= nil)

  -- A sheet and a map to draw FROM, seeded through the machine so both lanes
  -- see one picture: 0x0000-0x1fff is the sheet (and its top half doubles as
  -- map rows 32-63), 0x2000-0x2fff is the rest of the map.
  for a = 0x0000, 0x2fff do cpoke(a, (a * 37 + (a >> 5)) & 0xff) end
  for t = 0, 255 do m_fset(t, (t * 13) & 0xff) end

  local function lane(V, st, op, sheet)
    reset_draw()
    st(V)
    m_cls(0)
    local ok, r = pcall(op, V)
    return (ok and "ok" or "ERR") .. ":" .. tostring(r) .. ":" ..
           draw_digest(sheet) .. ":" .. V.pen() .. ":" .. V.cur()
  end

  for _, s in ipairs(STATES) do
    for _, o in ipairs(OPS) do
      same(o[1] .. " under " .. s[1],
           lane(LANE_C, s[2], o[2], o[3]), lane(LANE_L, s[2], o[2], o[3]))
    end
  end

  -- TILE 0 IS EMPTY, whichever way the cell was written. Both lanes above go
  -- through the same walk, so neither could see this: the SEED path maps p8's
  -- "sprite 0, empty by convention" onto cell 0, and the WRITE path stored a
  -- runtime 0 as cell 1 instead -- so `mset(x, y, 0)`, which is p8's only way
  -- to clear a cell, left one that drew sprite 0. Explicit rather than
  -- lane-compared for exactly that reason.
  reset_draw()
  for a = 0x0000, 0x0fff do cpoke(a, 0x77) end     -- sprites 0 and 1, solid 7
  __moy_mset(0, 0, 1)
  m_cls(0)
  __moy_p8_map(0, 0, 0, 0, 1, 1)
  check("a cell holding tile 1 draws it", __moy_p8_pget(0, 0) == 7)
  __moy_mset(0, 0, 0)
  m_cls(0)
  __moy_p8_map(0, 0, 0, 0, 1, 1)
  check("mset(x, y, 0) CLEARS the cell", __moy_p8_pget(0, 0) == 0)
  same("and mget reads the 0 back", __moy_mget(0, 0), 0)
  cpoke(0x2000, 0)
  m_cls(0)
  __moy_p8_map(0, 0, 0, 0, 1, 1)
  check("a poke of 0 into map memory clears it too", __moy_p8_pget(0, 0) == 0)

  -- The state the shim kept in Lua locals is the MEMORY MAP's now, so the
  -- verbs and peek/poke agree about it -- which is the whole reason it moved.
  reset_draw()
  __moy_p8_color(0x8b)
  check("color() writes the pen at 0x5f25", cpeek(0x5f25) == 0x8b)
  cpoke(0x5f25, 4)
  m_cls(0)
  __moy_p8_pset(3, 3)
  check("a poke at 0x5f25 IS the pen", __moy_p8_pget(3, 3) == 4)
  __moy_p8_cursor(17, 42)
  check("cursor() writes 0x5f26/0x5f27",
        cpeek(0x5f26) == 17 and cpeek(0x5f27) == 42)
  cpoke(0x5f26, 8) cpoke(0x5f27, 9)
  m_cls(0)
  __moy_p8_print("x")
  check("a poke at 0x5f26 moves the cursor", cpeek(0x5f27) == 15)
  __moy_p8_fillp(0x5a5a + 0.5)
  check("fillp() writes 0x5f31-0x5f33", cpeek(0x5f31) == 0x5a
        and cpeek(0x5f32) == 0x5a and cpeek(0x5f33) == 1)
  cpoke(0x5f31, 0xff) cpoke(0x5f32, 0xff)
  m_cls(3)
  __moy_p8_rectfill(0, 0, 20, 20, 7)
  check("a poke at 0x5f31 IS the fill pattern", __moy_p8_pget(0, 0) == 3)
  cpoke(0x5f33, 0)
  m_cls(3)
  __moy_p8_rectfill(0, 0, 20, 20, 0x27)
  check("and 0x5f33 is its transparency", __moy_p8_pget(0, 0) == 2)

  -- The SCREEN palette is memory too, so it survives the frame the console
  -- resets draw state on -- __moy_p8_frame is what puts it back.
  reset_draw()
  __moy_p8_pal(3, 0x8c, 1)
  check("pal(c, d, 1) writes 0x5f10", cpeek(0x5f13) == 0x8c)
  m_pal()                                     -- the console's per-frame reset
  __moy_p8_frame()
  check("the frame verb re-applies it", cpeek(0x5f13) == 0x8c)
  reset_draw()
end

function _init()
  font_checks()
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
  split_checks()
  rand_checks()
  bit_checks()
  native_bit_checks()
  map_checks()
  span_checks()
  span_verb_checks()
  draw_checks()
end

function _draw() cls(1) print("p8 stdlib: ok", 4, 60, 11) quit() end
