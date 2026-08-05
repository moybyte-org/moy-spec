#!/usr/bin/env bash
#
# Boot the ESP-IDF example under QEMU and check that the console actually runs.
#
#   . $IDF_PATH/export.sh
#   libmoy/test/esp_qemu.sh
#
# Compiling proves the component registers and the C is portable. It does not
# prove that a single line of it EXECUTES on an ESP32 -- and the four things a
# host owes libmoy are exactly the four that a compiler cannot check. So this
# boots the thing.
#
# Espressif's QEMU fork emulates esp32 (xtensa) and esp32c3; it does not do
# esp32p4, so this runs on esp32 with PSRAM, which the example needs for the
# 400 KB floor in SPEC.md 1.1. That is a different chip from the reference
# console and a different one again from whatever you are porting to, and it is
# still the difference between "it links" and "it runs".
#
# What it cannot tell you: whether a pixel reaches a panel, whether your GPIOs
# are the right way up, or whether the thing is fast enough. QEMU is not a
# timing model. Those need the board.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="$HERE/../example/esp-idf"
BUILD="${BUILD_DIR:-/tmp/moy-qemu}"
SECS="${QEMU_SECONDS:-20}"

if [ -z "${IDF_PATH:-}" ]; then
    echo "esp_qemu.sh: run '. \$IDF_PATH/export.sh' first" >&2
    exit 2
fi

# PSRAM because the console's buffers do not fit in an esp32's internal SRAM
# alongside a Lua VM. SPEC.md 12.4 excludes SRAM-only parts on purpose.
cat > "$BUILD.defaults" <<'CFG'
CONFIG_MOY_WITH_LUA=y
CONFIG_SPIRAM=y
CONFIG_SPIRAM_MODE_QUAD=y
CONFIG_SPIRAM_SPEED_80M=y
CONFIG_ESPTOOLPY_FLASHSIZE_4MB=y
CFG

echo "--- building for esp32 (PSRAM) ---"
idf.py -C "$PROJECT" -B "$BUILD" \
       -DSDKCONFIG="$BUILD.sdkconfig" \
       -DSDKCONFIG_DEFAULTS="$BUILD.defaults" \
       -DIDF_TARGET=esp32 build > "$BUILD.build.log" 2>&1 \
    || { tail -30 "$BUILD.build.log"; exit 1; }

# Boot twice against ONE flash image. The second boot is the whole point of
# doing it twice: persistence that never reaches flash looks identical to
# working persistence until something is power-cycled.
boot() {
    local n=$1 extra=()
    [ "$n" -gt 1 ] && extra=(--flash-file "$BUILD/qemu_flash.bin")
    echo "--- boot $n ---"
    timeout "$SECS" idf.py -C "$PROJECT" -B "$BUILD" qemu "${extra[@]}" \
        > "$BUILD.run$n.log" 2>&1 || true      # timeout kills it; that is the exit
    grep -E "moy:" "$BUILD.run$n.log" | head -4 || true
}

boot 1
boot 2

# -- what has to be true -------------------------------------------------- #

fail() { echo "FAIL: $*" >&2; exit 1; }

# Serial output carries CRs, and every grep below would otherwise be one \r away
# from a false negative. Strip them once. `|| true` on each extraction because
# set -o pipefail turns "matched nothing" into a silent exit 1 -- which reads as
# a passing test right up until you look at the exit code.
strip() { tr -d '\r' < "$1"; }
count() { grep -c "$1" || true; }
first() { grep -oE "$1" | head -1 || true; }

for n in 1 2; do
    log="$BUILD.run$n.log"
    clean="$BUILD.run$n.clean"
    strip "$log" > "$clean"

    grep -q "libmoy .* on ESP-IDF" "$clean" || fail "boot $n never reached app_main"
    if grep -qE "Guru Meditation|abort\(\) was called|panic" "$clean"; then
        fail "boot $n crashed"
    fi

    # It has to keep running, not just start. At 30 Hz and one line per 30
    # frames, a 20 s boot logs a few dozen; ten is a floor with slack for a
    # slow runner.
    frames=$(count "moy: frame " < "$clean")
    [ "$frames" -ge 10 ] || fail "boot $n logged only $frames frame lines"

    # ... and the raster has to be producing DIFFERENT frames. A console stuck
    # on one image still logs happily; the cart animates, so the checksum of
    # the index framebuffer must move.
    distinct=$( (grep -oE "frame [0-9a-f]{8}" "$clean" || true) | sort -u | wc -l)
    [ "$distinct" -ge 2 ] || fail "boot $n drew the same frame every time"
done

# The one that needed two boots.
p1=$(first "pmem\[0\] = -?[0-9]+" < "$BUILD.run1.clean" | grep -oE -- "-?[0-9]+$" || true)
p2=$(first "pmem\[0\] = -?[0-9]+" < "$BUILD.run2.clean" | grep -oE -- "-?[0-9]+$" || true)
[ -n "$p1" ] && [ -n "$p2" ] || fail "no pmem[0] line (boot1='$p1' boot2='$p2')"
[ "$p2" -eq $((p1 + 1)) ] || fail "pmem did not survive the reboot: $p1 then $p2"

echo
echo "ran on emulated esp32: two boots, no crash, frames advancing,"
echo "pmem[0] $p1 -> $p2 across a power cycle."
