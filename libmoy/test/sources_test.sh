#!/usr/bin/env bash
# SPEC.md 4's `sources`, asserted against the real loader.
#
#   libmoy/test/sources_test.sh [path/to/run_cart]
#
# Three claims, and each one is a thing a host could plausibly get wrong while
# still running a one-file cart perfectly:
#
#   ORDER      the scripts run in the listed order, so a prologue's globals
#              exist before the game reads them and an epilogue can wrap what
#              the game defined.
#   CHUNKS     each script is its own chunk, so a `local` does not cross.
#              Concatenating the files would pass every other check here.
#   REFUSAL    a `sources` the host cannot follow refuses the cart instead of
#              loading the part that parsed. A cart run without its prologue
#              fails inside the author's code, which sends the reader the
#              wrong way -- that is the whole reason the field is not one a
#              host may ignore (SPEC.md 3.1).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN="${1:-${HERE}/../build/run_cart}"
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

cart() {                       # cart <dir> <sources-json>
  mkdir -p "${WORK}/$1"
  printf '{"format":"moy-1","title":"s","main":"main.lua","canvas":"128x128","sources":%s}\n' \
    "$2" > "${WORK}/$1/manifest.json"
}

fail() { echo "sources_test: $*" >&2; exit 1; }

# -- 1. order, and chunk isolation ------------------------------------------
cart ok '["pro.lua","main.lua","epi.lua"]'
cat > "${WORK}/ok/pro.lua" <<'LUA'
local invisible = "prologue"
ORDER = "p"
function shared() return 3 end
LUA
cat > "${WORK}/ok/main.lua" <<'LUA'
ORDER = ORDER .. "m"
if shared() ~= 3 then error("a prologue global did not reach main") end
if invisible ~= nil then error("a prologue LOCAL reached main: one chunk, not three") end
function _draw() cls(1) circ(40, 40, shared(), 10) end
LUA
cat > "${WORK}/ok/epi.lua" <<'LUA'
ORDER = ORDER .. "e"
if ORDER ~= "pme" then error("scripts ran out of order: " .. ORDER) end
local wrapped = _draw
if wrapped == nil then error("main.lua's _draw was not there to wrap") end
function _draw() wrapped() print("e", 4, 4, 7) end
LUA
"${RUN}" "${WORK}/ok" "${WORK}/ok.bin" --frames 2 >/dev/null \
  || fail "a three-script cart did not run"

# -- 2. the default: no `sources` is a one-file cart -------------------------
mkdir -p "${WORK}/plain"
printf '{"format":"moy-1","title":"s","main":"main.lua","canvas":"128x128"}\n' \
  > "${WORK}/plain/manifest.json"
printf 'function _draw() cls(1) end\n' > "${WORK}/plain/main.lua"
"${RUN}" "${WORK}/plain" "${WORK}/plain.bin" --frames 2 >/dev/null \
  || fail "a cart with no \"sources\" stopped working"

# -- 3. the refusals ---------------------------------------------------------
refuse() {                     # refuse <dir> <sources-json> <what>
  cart "$1" "$2"
  printf 'function _draw() cls(1) end\n' > "${WORK}/$1/main.lua"
  printf 'X = 1\n' > "${WORK}/$1/pro.lua"
  if "${RUN}" "${WORK}/$1" "${WORK}/$1.bin" --frames 1 >/dev/null 2>&1; then
    fail "ran a cart whose \"sources\" $3"
  fi
}
refuse nomain  '["pro.lua"]'                    "does not list main (SPEC.md 4)"
refuse missing '["ghost.lua","main.lua"]'       "names a file the cart does not hold"
refuse twice   '["pro.lua","pro.lua","main.lua"]' "names the same script twice"
refuse notlist '"pro.lua"'                      "is a string rather than a list"

echo "sources_test: order, chunk isolation, the default and four refusals"
