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
  bit_checks()
  map_checks()
  span_checks()
end

function _draw() cls(1) print("p8 stdlib: ok", 4, 60, 11) quit() end
