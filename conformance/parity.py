"""Prove moycore renders what the reference console renders -- byte for byte.

moycore was EXTRACTED from the reference implementation (moybyte), so the claim
that it draws the same pixels is a claim about a refactor, and a refactor is
exactly the kind of thing that can be checked mechanically instead of asserted.
This replays every conformance scene through both rasterizers and compares the
framebuffers.

It is also the honest answer to a fair objection: a second implementation of
the same raster is a liability if it drifts. This is the thing that makes drift
loud.

Run it with the reference checkout available:

    python3 conformance/parity.py --ref /path/to/moybyte

Without --ref it looks in a few usual places and skips (exit 0, loudly) if it
cannot find one -- so this is a developer check, not something that breaks a
clone for someone who only has the spec repo.

WHAT THIS IS NOT: conformance. SPEC.md 11 makes the WebAssembly player the
tiebreaker for golden frames, and this compares two Python rasterizers to each
other. It proves the extraction faithful. Binding the goldens to the wasm player
is a separate job that needs a browser harness.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import moycore                                    # noqa: E402
from conformance import scenes                    # noqa: E402

REF_CANDIDATES = (
    os.environ.get("MOYBYTE"),
    os.path.expanduser("~/Documents/Work/kidcode"),
    os.path.expanduser("~/work/kidcode"),
    os.path.expanduser("~/moybyte"),
)


def find_ref(explicit=None):
    for path in ((explicit,) if explicit else REF_CANDIDATES):
        if path and os.path.isfile(os.path.join(path, "runtime", "canvas.py")):
            return path
    return None


def build_ref(ref_path):
    """Import the reference console's canvas + assets."""
    sys.path.insert(0, ref_path)
    from runtime import canvas as ref_canvas
    from runtime import editors_sheet as ref_sheet
    return ref_canvas, ref_sheet


def _describe_diff(a, b, w=320):
    """Where the two buffers first disagree, and how badly."""
    n = min(len(a), len(b))
    first = None
    count = 0
    for i in range(n):
        if a[i] != b[i]:
            count += 1
            if first is None:
                first = i
    if first is None:
        return None
    return {
        "count": count,
        "total": n,
        "x": first % w,
        "y": first // w,
        "ref": a[first],
        "core": b[first],
    }


def run(ref_path, verbose=False):
    ref_canvas, ref_sheet_mod = build_ref(ref_path)

    failures = []
    for name, fn in scenes.SCENES:
        if name in scenes.EXCLUDED:
            # Provisional scenes (SPEC.md 6.1) exercise verbs moycore no
            # longer carries; run.py excludes them from counting and parity
            # cannot execute them at all.
            if verbose:
                print("  --    %s  (excluded)" % name)
            continue
        # The reference sheet is built at the SPEC's dimensions (16x32 tiles,
        # SPEC.md 3.2) rather than its own 16x16 default, so tile ids past 255
        # exist on both sides and the comparison is about rasterization rather
        # than about sheet size.
        rs = ref_sheet_mod.SpriteSheet(16, 32)
        rt = ref_sheet_mod.TileMap(20, 15)
        scenes._fill_sheet(rs)
        scenes._fill_map(rt)
        rc = ref_canvas.Canvas(320, 240)
        fn(rc, rs, rt)
        flush = getattr(rc, "flush_batch", None)
        if flush is not None:
            flush()          # the reference auto-batches sprites; moycore does not

        cs = moycore.SpriteSheet()
        ct = moycore.TileMap(20, 15)
        scenes._fill_sheet(cs)
        scenes._fill_map(ct)
        cc = moycore.Canvas()
        fn(cc, cs, ct)

        diff = _describe_diff(rc.buf, cc.buf)
        if diff is None:
            if verbose:
                print("  ok    %s" % name)
        else:
            failures.append((name, diff))
            print("  FAIL  %s: %d/%d pixels differ; first at (%d, %d) "
                  "reference=%d moycore=%d"
                  % (name, diff["count"], diff["total"], diff["x"], diff["y"],
                     diff["ref"], diff["core"]))
    return failures


def main(argv):
    explicit = None
    verbose = "-v" in argv or "--verbose" in argv
    if "--ref" in argv:
        explicit = argv[argv.index("--ref") + 1]
    ref = find_ref(explicit)
    if ref is None:
        print("parity: no reference implementation found -- skipping.")
        print("        pass --ref /path/to/moybyte (or set MOYBYTE) to run it.")
        return 0
    print("parity: moycore vs %s" % ref)
    failures = run(ref, verbose)
    if failures:
        print("\n%d of %d scenes differ." % (len(failures), len(scenes.SCENES)))
        return 1
    print("all %d scenes byte-identical." % len(scenes.SCENES))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
