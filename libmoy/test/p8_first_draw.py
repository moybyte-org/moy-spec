"""_draw runs after _update on every tick, and runs without one.

    python3 libmoy/test/p8_first_draw.py        (`make -C libmoy p8-test`)

The host paces the cart (SPEC.md 5): one _update call is one tick, and _draw
never runs before the first one. The shim keeps a guard for that, and a cart
may rely on it -- dank_tomb creates its player light in _init and only
positions it in the first update, so a draw with no tick behind it indexed a
nil position. run_cart calls update then draw on every frame whatever --dt it
is handed, so at a frame period far shorter than the cart's the tick still
comes first and the frame carries what the update placed.

Two carts:

  p8_first_draw.p8   an _update60 cart whose _draw needs the update's state:
                     it draws at dt = 1/125 and at dt = 1/30 alike.
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
    for dt in (1.0 / 125.0, 1.0 / 30.0):
        got = frame(cart, dt)
        if 7 not in set(got):
            raise SystemExit("p8 first draw: at dt=%s the first frame drew "
                             "nothing the update placed (colours %s)"
                             % (dt, sorted(set(got))))

    only = frame(port("p8_draw_only"), 1.0 / 125.0)
    if set(only) != {7}:
        raise SystemExit("p8 first draw: a cart with no update must draw every "
                         "frame, and drew %s" % sorted(set(only)))
    print("p8 first draw: the tick comes first at every frame period, and a "
          "cart with no update draws without one")
    return 0


if __name__ == "__main__":
    sys.exit(main())
