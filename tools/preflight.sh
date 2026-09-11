#!/usr/bin/env bash
# Run what CI runs, here, before pushing.
#
#   tools/preflight.sh            # everything
#   tools/preflight.sh --fast     # skip the wasm half (no Docker pull)
#
# WHY THIS EXISTS. `make -C libmoy test` is not the CI job -- it is the part of
# it that needs nothing but a C compiler. The steps it leaves out are the ones
# that check a COMMITTED ARTIFACT against the sources it was built from, and
# those are exactly the ones that break when you change a source and forget the
# artifact. On 2026-09-11 a one-line change to `libmoy/port/moy_manifest.h`
# (MOY_SOURCES_MAX) left `runner/` stale; `make test` was green, the push was
# red, and the round trip cost a CI run to discover something a local command
# already knew how to say.
#
# WHY DOCKER. The wasm steps need emscripten, and WHICH emscripten is not a
# detail: emcc is not byte-reproducible across versions, so a rebuild on a
# different one produces a different `moy.wasm` and a different stamp. This
# machine had 6.0.4 and the committed player was built with 6.0.7, so building
# locally would have silently DOWNGRADED the artifact while making CI green.
# A pinned image is the only way the toolchain is a fact rather than whatever
# was installed. (CI itself installs `emsdk latest`, which is how the pin moves;
# when it does, bump EMSDK_IMAGE here and rebuild in the same commit.)
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SPEC="$(cd "${HERE}/.." && pwd)"
cd "${SPEC}"

EMSDK_IMAGE="${EMSDK_IMAGE:-emscripten/emsdk:6.0.7}"
CFLAGS_CI="-std=c99 -O2 -Wall -Wextra -Wpedantic -Wshadow -Wconversion -Wstrict-prototypes -Werror -Iinclude"
FAST=0
[ "${1:-}" = "--fast" ] && FAST=1

fails=0
step() {                        # step "name" cmd...
  local name="$1"; shift
  printf '== %s\n' "${name}"
  if "$@" > /tmp/preflight.$$ 2>&1; then
    printf '   ok\n'
  else
    printf '   FAIL\n'
    sed 's/^/   | /' /tmp/preflight.$$ | tail -25
    fails=$((fails + 1))
  fi
  rm -f /tmp/preflight.$$
}

step "build"                 make -C libmoy CFLAGS="${CFLAGS_CI}"
step "docs agree"            python3 tools/check_docs.py
step "libmoy suite"          make -C libmoy test

# The artifact checks. `moy.py player` is the cheap one and catches the whole
# class on its own -- it compares the committed bundle's stamp against a hash of
# the sources in this tree, so it answers without emscripten at all.
step "committed player matches its stamp" python3 moy.py player

if [ "${FAST}" = "1" ]; then
  printf '== (skipping the wasm rebuild: --fast)\n'
else
  if ! docker info >/dev/null 2>&1; then
    printf '== FAIL wasm steps: no docker daemon (or run with --fast)\n'
    fails=$((fails + 1))
  else
    # A REBUILD, compared. The stamp above says the sources changed; this says
    # the committed page and shim are what those sources produce. The wasm
    # itself is not compared -- emcc is not byte-reproducible -- which is why
    # the stamp check above is the one that judges it.
    cp runner/index.html /tmp/pf-index.html
    cp runner/player.js  /tmp/pf-player.js
    step "runner/ is what libmoy/port/wasm builds" \
      docker run --rm -v "${SPEC}":/src -w /src -u "$(id -u):$(id -g)" \
        "${EMSDK_IMAGE}" libmoy/port/wasm/build.sh
    step "  ...the committed page is the built page" \
      bash -c 'diff /tmp/pf-index.html runner/index.html && diff /tmp/pf-player.js runner/player.js'
    rm -f /tmp/pf-index.html /tmp/pf-player.js
    if command -v node >/dev/null 2>&1; then
      step "web player conformance" \
        python3 conformance/run.py --player "node libmoy/port/wasm/conform.mjs {cart} {out}"
      step "the committed player has every core verb" \
        node libmoy/port/wasm/conform.mjs libmoy/test/core_verbs.moy /tmp/pf-cv.bin
    else
      printf '== (no node: skipping the two player conformance steps)\n'
    fi
  fi
fi

if [ "${fails}" -ne 0 ]; then
  printf '\npreflight: %d step(s) failed -- CI would too.\n' "${fails}"
  exit 1
fi
printf '\npreflight: green. A push should be too.\n'
