#!/usr/bin/env bash
# Build the browser player: libmoy + Lua + main.c through emscripten, plus the
# page, into runner/ at the top of this repository.
#
#   ./build.sh                 # build into ../../../runner
#   ./build.sh /tmp/out        # build somewhere else
#   EMSDK=~/emsdk ./build.sh   # point at an emsdk checkout to source
#
# emcc is the only tool this needs. If it is not on PATH, set EMSDK to a
# checkout of emscripten-core/emsdk and this sources its env for you.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIBMOY="$(cd "${HERE}/../.." && pwd)"
SPEC="$(cd "${LIBMOY}/.." && pwd)"
OUT="${1:-${SPEC}/runner}"

if ! command -v emcc >/dev/null 2>&1; then
  if [ -n "${EMSDK:-}" ] && [ -f "${EMSDK}/emsdk_env.sh" ]; then
    # shellcheck disable=SC1091
    source "${EMSDK}/emsdk_env.sh" >/dev/null 2>&1
  fi
fi
command -v emcc >/dev/null 2>&1 || {
  echo "build.sh: no emcc. Install emscripten, or set EMSDK to an emsdk checkout:" >&2
  echo "  git clone https://github.com/emscripten-core/emsdk && cd emsdk \\" >&2
  echo "    && ./emsdk install latest && ./emsdk activate latest" >&2
  exit 1
}

mkdir -p "${OUT}"
# Clear the previous bundle, keeping this repository's own files. Without this
# the output is a UNION of every player ever built here, and the stamp would
# faithfully hash files nothing loads.
find "${OUT}" -maxdepth 1 -type f \
  ! -name VERSION ! -name BUILD.md ! -name THIRD_PARTY.md ! -name LICENSE.txt -delete

# The exported surface, and nothing else: every name here is called by page.js
# and each one is in main.c with EMSCRIPTEN_KEEPALIVE beside it.
EXPORTS='["_main","_malloc","_free"'
EXPORTS+=',"_moy_web_reset","_moy_web_file","_moy_web_boot","_moy_web_frame"'
EXPORTS+=',"_moy_web_button","_moy_web_touch","_moy_web_key"'
EXPORTS+=',"_moy_web_pixels","_moy_web_indices"'
EXPORTS+=',"_moy_web_width","_moy_web_height","_moy_web_fps"'
EXPORTS+=',"_moy_web_title","_moy_web_error","_moy_web_running","_moy_web_textmode"'
EXPORTS+=',"_moy_web_audio","_moy_web_audio_rate","_moy_web_audio_wanted"'
EXPORTS+=',"_moy_web_pmem","_moy_web_pmem_moved","_moy_web_pmem_clean"]'

# Lua's own warnings are not ours to fix (-w), and it is built from source here
# for the same reason the desktop port does: the VM is a build choice, and
# vendor/lua is the one SPEC.md 4.2 pins (LUA_32BITS, sandboxed sources).
SRC=(
  "${HERE}/main.c"
  "${LIBMOY}/src/moy_canvas.c"
  "${LIBMOY}/src/moy_sprite.c"
  "${LIBMOY}/src/moy_data.c"
  "${LIBMOY}/src/moy_audio.c"
  "${LIBMOY}/src/moy_lua.c"
)
for f in "${LIBMOY}"/vendor/lua/*.c; do SRC+=("$f"); done

echo "== emcc $(emcc -dumpversion 2>/dev/null || true)"
emcc -O3 -w -std=gnu99 \
  -DMOY_WITH_LUA \
  -I"${LIBMOY}/include" -I"${LIBMOY}/vendor/lua" \
  "${SRC[@]}" \
  -sMODULARIZE=1 -sEXPORT_NAME=createMoy -sEXPORT_ES6=1 \
  -sENVIRONMENT=web,worker,node \
  -sFILESYSTEM=0 -sALLOW_MEMORY_GROWTH=1 -sINITIAL_MEMORY=16MB \
  -sEXPORTED_FUNCTIONS="${EXPORTS}" \
  -sEXPORTED_RUNTIME_METHODS='["ccall","cwrap","UTF8ToString","stringToUTF8","lengthBytesUTF8","HEAPU8","HEAP32","HEAPF32","HEAPU32"]' \
  --closure 0 \
  -o "${OUT}/moy.mjs"

cp "${HERE}/page/index.html" "${OUT}/index.html"
cp "${HERE}/page/player.js"  "${OUT}/player.js"

# The stamp: which build these files are, and a hash per file. `moy.py player`
# reads it, and a mismatch means someone edited the bundle by hand instead of
# the source it came from -- which is the failure worth catching, because the
# edit would survive right up until the next rebuild silently reverted it.
# The dirty flag excludes OUT, because OUT is what this script just wrote: asking
# git about the whole tree here made every stamp ever produced say "dirty", which
# is the same as saying nothing.
REL_OUT="$(python3 -c 'import os,sys; print(os.path.relpath(sys.argv[1], sys.argv[2]))' "${OUT}" "${SPEC}")"
python3 - "${OUT}" "$(cd "${SPEC}" && git rev-parse HEAD 2>/dev/null || echo '')" \
          "$(cd "${SPEC}" && git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '')" \
          "$(cd "${SPEC}" && git status --porcelain -- . ":(exclude)${REL_OUT}" 2>/dev/null | head -c1)" \
          "$(emcc -dumpversion 2>/dev/null || echo '?')" \
          "$(python3 "${HERE}/inputs.py" "${SPEC}")" <<'PY'
import hashlib, json, os, sys
out, commit, branch, dirty, emcc, inputs = sys.argv[1:7]
skip = {"VERSION", "BUILD.md", "THIRD_PARTY.md", "LICENSE.txt"}
files = {}
for name in sorted(os.listdir(out)):
    path = os.path.join(out, name)
    if name in skip or not os.path.isfile(path):
        continue
    with open(path, "rb") as f:
        data = f.read()
    files[name] = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
stamp = {
    "bundle": "moy web player (libmoy/port/wasm)",
    "source": {"commit": commit, "branch": branch, "dirty": bool(dirty)},
    "toolchain": "emscripten " + emcc,
    # What it was compiled FROM, recomputable without git (inputs.py).
    "inputs_sha256": inputs,
    "files": files,
}
with open(os.path.join(out, "VERSION"), "w", encoding="utf-8", newline="\n") as f:
    json.dump(stamp, f, indent=2, sort_keys=True)
    f.write("\n")
print("== %d files, %d bytes total"
      % (len(files), sum(v["bytes"] for v in files.values())))
PY

echo "== built into ${OUT}"
ls -l "${OUT}"/moy.wasm "${OUT}"/moy.mjs "${OUT}"/index.html "${OUT}"/player.js
