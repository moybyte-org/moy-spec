"""Run imported PICO-8 carts through libmoy, here, where the porter lives.

    python3 conformance/p8_carts.py                 # needs a cart corpus
    python3 conformance/p8_carts.py --corpus DIR

WHY THIS IS IN THIS REPOSITORY and not in a host's.

The porter is `p8_lua_port.py`, three files up. A host VENDORS it, so a bug
introduced here is only noticed when someone re-vendors and runs that host's
suite -- which is exactly the delay that let the PICO-8 pitch offset be wrong
for ten days. libmoy is in-tree for this reason (see .github/workflows/
libmoy.yml) and the porter deserves the same treatment: red on the same push.

It is also the VM the porter's output has to survive: libmoy builds Lua with
LUA_32BITS, so lua_Number is a single-precision float and `0xffff.fffe` is
already 65536.0 by the time a cart can see it. A faithful 16.16 fixed-point
implementation of p8's bitwise operators was written on 2026-09-01 and returns
0 here.

That is NOT because hosts run a different Lua -- moybyte's host runs this
binding over this vendored Lua, LUA_32BITS and all, and deleted its lupa lane
in 2026-08-14 precisely so it would. What actually happened is worse and worth
recording: the fixed-point work was validated in a throwaway `lupa` script,
which is 64-bit, and lupa is the second embedding this project already threw
out for exactly that reason. The lesson is not "test upstream", it is "do not
check numeric semantics on a Lua nobody ships".

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
FRAMES = 200
# A cart that spins gets ONE chance to prove it, not three: `terra` never
# returns, and running the held and unheld passes anyway turned a two-minute
# suite into a six-minute one for a result already known after the first.
TIMEOUT_S = 45

# Most carts want a button before anything moves, and they do not agree on
# which -- so press several, spaced, and give the cart time between. A start
# screen that never gets its button looks exactly like a cart that does not
# run, which is the confusion these two numbers exist to separate.
START = "a@30-34,b@70-74,a@110-114,up@150-154"
MOVE = START + ",right@170-190,left@192-199"


def _frame_hash(path):
    with open(path, "rb") as fh:
        return hashlib.blake2b(fh.read(), digest_size=8).hexdigest()


def check(cart_path, work):
    """-> (runs, animates, responds, note).

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
        return False, False, False, "import %s: %s" % (type(exc).__name__, exc)

    # Two runs at different frame counts: if the cart is ANIMATING the frames
    # differ, and if it is frozen (or never ticked) they do not. A cart that
    # never runs also never errors, so a clean exit proves nothing on its own.
    def frame_at(frames, hold, tag):
        dump = os.path.join(work, "%s.%s.bin" % (name, tag))
        cmd = [RUN_CART, out_dir, dump, "--frames", str(frames)]
        if hold:
            cmd += ["--hold", hold]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired:
            return None, "HUNG (no frame in %ds)" % TIMEOUT_S
        if r.returncode != 0:
            return None, (r.stderr.strip() or r.stdout.strip() or
                          "run_cart exit %d" % r.returncode)[:140]
        if not os.path.exists(dump):
            return None, "run_cart wrote no frame"
        return _frame_hash(dump), None

    early, err = frame_at(2, None, "early")
    if err:
        return False, False, False, err
    late, err = frame_at(FRAMES, MOVE, "move")
    if err:
        return False, False, False, err          # a hang stops here
    idle, err = frame_at(FRAMES, START, "idle")
    if err:
        return False, False, False, err

    moves = early != late
    # RESPONDS: the same cart, same frame count, differing only in whether a
    # direction was held. Two runs are what makes that a measurement rather
    # than a guess -- one run cannot tell motion from reaction.
    responds = late != idle
    note = ("runs and animates" if moves else "runs, but the frame never changed")
    if responds:
        note += "; takes input"
    return True, moves, responds, note


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

    # A cart marked `unstable` FLAPPED across the runs its pin was taken from --
    # petal_quest sits on a title and stops on cocreate at a variable point, so
    # whether it animates inside the frame budget is a coin toss. It is still
    # gated on `runs`, which is stable; it is simply not judged on the two
    # signals it cannot hold steady. Naming the one flaky cart is honest, and
    # it beats loosening the gate for the eleven that are not.
    #
    # `responds` is gated only DOWNWARD. A cart on the edge of getting past its
    # title -- petal_quest dies on cocreate at a variable point -- flips it
    # between runs, and failing the build because a flaky signal turned ON is
    # noise. It still fails if a cart that reliably took input stops.
    regressed, improved, running = [], [], 0
    for f in carts:
        stem = f.split(".p8")[0]
        ok, moves, responds, note = check(os.path.join(args.corpus, f), args.work)
        running += 1 if ok else 0
        want = expected.get(stem, {})
        shaky = bool(want.get("unstable"))
        mark = "ok" if ok else "FAIL"
        if want.get("runs") is True and not ok:
            regressed.append("%s stopped running: %s" % (stem, note))
        elif want.get("animates") is True and not moves and not shaky:
            regressed.append("%s stopped animating: %s" % (stem, note))
        elif want.get("responds") is True and not responds and not shaky:
            regressed.append("%s stopped taking input: %s" % (stem, note))
        elif want.get("runs") is False and ok:
            improved.append("%s runs now" % stem)
            mark = "NEW"
        elif want.get("animates") is False and moves and not shaky:
            improved.append("%s animates now" % stem)
            mark = "NEW"
        elif shaky:
            mark = "shaky"
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
