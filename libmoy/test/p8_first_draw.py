"""_draw does not run before the first _update tick -- and does run without one.

    python3 libmoy/test/p8_first_draw.py        (`make -C libmoy p8-test`)

The shim paces the cart itself (SPEC.md 5's sanctioned degradation), so a
console frame SHORTER than one cart period leaves it with nothing to draw yet.
It used to draw anyway: `ticked` started true, so the very first _draw ran with
no update behind it. PICO-8 never does that, and a cart may rely on it --
dank_tomb creates its player light in _init and only positions it in the first
update, so its _draw indexed a nil position on a board whose first frame
arrived inside 1/60s. Four runs in five on the P4, eight in nine on a T-Deck;
never here, because run_cart's frame was a fixed 1/30 and always ticked first.

Two carts and two frame periods, which is what makes it a measurement:

  p8_first_draw.p8   an _update60 cart whose _draw needs the update's state.
                     At dt = 1/125 nothing has ticked, so nothing may be
                     drawn; at dt = 1/30 two ticks have run and it draws.
  p8_draw_only.p8    no update function at all -- there is no tick to wait
                     for, so it draws on the first frame like PICO-8's does.

CORPUS-INDEPENDENT on purpose: these two carts are three lines each and live
here, so the regression is checked on every build rather than when someone
happens to have twelve BBS carts on disk.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

import p8_import                                              # noqa: E402
import p8_lua_port                                            # noqa: E402

RUN_CART = os.path.join(ROOT, "libmoy", "build", "run_cart")
WORK = os.path.join(ROOT, "libmoy", "build")


def port(stem):
    out = os.path.join(WORK, stem + ".moy")
    p8_lua_port.port_sections(p8_import.read_p8(os.path.join(HERE, stem + ".p8")),
                              out, stem)
    return out


def frame(cart, dt, frames=1):
    """-> the dumped frame, or SystemExit naming what run_cart said."""
    dump = os.path.join(WORK, "first_draw.bin")
    r = subprocess.run([RUN_CART, cart, dump, "--frames", str(frames),
                        "--dt", str(dt)], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit("p8 first draw: %s at dt=%s: %s"
                         % (os.path.basename(cart), dt,
                            (r.stderr or r.stdout).strip()))
    with open(dump, "rb") as fh:
        return fh.read()


def main():
    cart = port("p8_first_draw")
    early = frame(cart, 1.0 / 125.0)
    if set(early) != {0}:
        raise SystemExit("p8 first draw: a frame shorter than one cart period "
                         "ticked nothing, and _draw ran anyway (%d colours)"
                         % len(set(early)))
    late = frame(cart, 1.0 / 30.0)
    if 7 not in set(late):
        raise SystemExit("p8 first draw: a frame long enough to tick drew "
                         "nothing (colours %s)" % sorted(set(late)))

    only = frame(port("p8_draw_only"), 1.0 / 125.0)
    if set(only) != {7}:
        raise SystemExit("p8 first draw: a cart with no update must draw every "
                         "frame, and drew %s" % sorted(set(only)))
    print("p8 first draw: _draw waits for the first tick, and draws without one")
    return 0


if __name__ == "__main__":
    sys.exit(main())
