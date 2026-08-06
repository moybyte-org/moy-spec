#!/bin/sh
# Adapt moy-spec's player protocol to the trace replayer.
#
#   replay_cart.sh <cart-dir> <out-file>
#
# run.py hands a player a CART, because that is what a finished host runs.
# libmoy has no Lua VM yet, so it consumes the same scene in its other published
# form -- the verb trace beside the cart -- and takes the sheet and tilemap from
# the cart folder itself. Deriving the trace path here rather than teaching
# run.py about traces keeps the protocol one thing: a command, a cart, a frame.
set -eu

cart=$1
out=$2
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

name=$(basename "$cart")
name=${name%.moy}
trace=$(dirname "$cart")/../traces/$name.json

if [ ! -f "$trace" ]; then
    echo "replay_cart.sh: no trace for $name at $trace" >&2
    echo "  (regenerate with: python3 conformance/build.py)" >&2
    exit 2
fi

set -- "$trace" "$out"
[ -f "$cart/sprites.moygfx" ] && set -- "$@" --sheet "$cart/sprites.moygfx"
[ -f "$cart/map.moymap" ]     && set -- "$@" --map   "$cart/map.moymap"

# MOY_REPLAY picks which build of the replayer runs -- the index one by
# default, the direct-colour one for `make conform-565`. Same suite, same
# goldens, different pixel format underneath.
exec "${MOY_REPLAY:-$here/../build/trace_replay}" "$@"
