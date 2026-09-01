"""Run imported PICO-8 carts through libmoy, here, where the porter lives.

    python3 conformance/p8_carts.py                 # needs a cart corpus
    python3 conformance/p8_carts.py --corpus DIR

WHY THIS IS IN THIS REPOSITORY and not in a host's.

The porter is `p8_lua_port.py`, three files up. A host VENDORS it, so a bug
introduced here is only noticed when someone re-vendors and runs that host's
suite -- which is exactly the delay that let the PICO-8 pitch offset be wrong
for ten days. libmoy is in-tree for this reason (see .github/workflows/
libmoy.yml) and the porter deserves the same treatment: red on the same push.

And it is not merely earlier, it is a DIFFERENT MACHINE. libmoy builds Lua with
LUA_32BITS, which makes lua_Number a single-precision float. A host testing
against a desktop Lua is testing 64-bit integers and doubles. On 2026-09-01 a
faithful 16.16 fixed-point implementation of p8's bitwise operators passed
every host test and returned 0 here, because `0xffff.fffe` is already 65536.0
by the time a cart on this VM can see it. Only this runner could have said so.

A RATCHET, like the goldens: `p8_carts_expected.json` records which carts run
today, so a known failure does not break the build and a REGRESSION does. A
cart that starts running fails too, asking for the file to be raised.

THE CARTS ARE NOT IN THIS REPOSITORY. They are their authors' work, several
under licences that forbid redistribution. Point --corpus at a directory of
`.p8` / `.p8.png` files; without one this skips and says so.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import p8_import                                              # noqa: E402
import p8_lua_port                                            # noqa: E402

RUN_CART = os.path.join(ROOT, "libmoy", "build", "run_cart")
EXPECTED = os.path.join(HERE, "p8_carts_expected.json")
FRAMES = 90


def _frame_hash(path):
    with open(path, "rb") as fh:
        return hashlib.blake2b(fh.read(), digest_size=8).hexdigest()


def check(cart_path, work):
    """-> (runs, animates, note).

    Both matter and they fail differently. A cart that never ticks still LOADS
    and still writes a frame, so `runs` alone cannot see a driver that stopped
    calling the cart's update -- only the frame CHANGING can.
    """
    name = os.path.basename(cart_path).split(".p8")[0]
    out_dir = os.path.join(work, name + ".moy")
    try:
        sections = p8_import.read_p8(cart_path)
        p8_lua_port.port_sections(sections, out_dir, name)
    except Exception as exc:                       # noqa: BLE001 - reported
        return False, False, "import %s: %s" % (type(exc).__name__, exc)

    # Two runs at different frame counts: if the cart is ANIMATING the frames
    # differ, and if it is frozen (or never ticked) they do not. A cart that
    # never runs also never errors, so a clean exit proves nothing on its own.
    shots = []
    for frames in (2, FRAMES):
        dump = os.path.join(work, "%s.%d.bin" % (name, frames))
        try:
            r = subprocess.run([RUN_CART, out_dir, dump, "--frames", str(frames)],
                               capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired:
            return False, False, "HUNG (no frame in 120s)"
        if r.returncode != 0:
            return False, False, (r.stderr.strip() or r.stdout.strip() or
                                  "run_cart exit %d" % r.returncode)[:140]
        if not os.path.exists(dump):
            return False, False, "run_cart wrote no frame"
        shots.append(_frame_hash(dump))
    if shots[0] == shots[1]:
        return True, False, "runs, but the frame never changed"
    return True, True, "runs and animates"


def main(argv):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", default=os.environ.get("MOY_P8_CORPUS"))
    ap.add_argument("--work", default="/tmp/moy_p8_carts")
    args = ap.parse_args(argv[1:])

    if not args.corpus or not os.path.isdir(args.corpus):
        print("no cart corpus (--corpus DIR or MOY_P8_CORPUS); skipping")
        return 0
    if not os.path.exists(RUN_CART):
        print("libmoy/build/run_cart is not built -- `make -C libmoy lua`")
        return 2

    os.makedirs(args.work, exist_ok=True)
    carts = sorted(f for f in os.listdir(args.corpus)
                   if f.endswith(".p8") or f.endswith(".p8.png"))
    if not carts:
        print("no carts in %s; skipping" % args.corpus)
        return 0

    expected = {}
    if os.path.exists(EXPECTED):
        with open(EXPECTED, encoding="utf-8") as fh:
            expected = json.load(fh).get("carts", {})

    regressed, improved, running = [], [], 0
    for f in carts:
        stem = f.split(".p8")[0]
        ok, moves, note = check(os.path.join(args.corpus, f), args.work)
        running += 1 if ok else 0
        want = expected.get(stem, {})
        mark = "ok" if ok else "FAIL"
        if want.get("runs") is True and not ok:
            regressed.append("%s stopped running: %s" % (stem, note))
        elif want.get("animates") is True and not moves:
            regressed.append("%s stopped animating: %s" % (stem, note))
        elif want.get("runs") is False and ok:
            improved.append("%s runs now" % stem)
            mark = "NEW"
        elif want.get("animates") is False and moves:
            improved.append("%s animates now" % stem)
            mark = "NEW"
        elif want.get("runs") is False:
            mark = "known"          # a recorded failure, not a build breaker
        print("  %-28s %-5s %s" % (stem[:28], mark, note))

    print("\n%d/%d carts run under libmoy" % (running, len(carts)))
    if regressed:
        print("\nREGRESSED -- these ran before:")
        for r in regressed:
            print("  " + r)
    if improved:
        print("\nIMPROVED -- raise conformance/p8_carts_expected.json:")
        for r in improved:
            print("  " + r)
    if not expected:
        print("\n(no expectations file; nothing is being gated)")
    return 1 if (regressed or improved) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
