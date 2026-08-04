"""Run the conformance suite against an implementation.

    python3 conformance/run.py                       # check moycore (self-test)
    python3 conformance/run.py --player "CMD"        # check anything else
    python3 conformance/run.py --diff out/           # write per-scene diff PNGs

SPEC.md 11: "An implementation conforms when it runs the conformance suite and
produces pixel-identical output." This is the runner that decides.

THE PLAYER PROTOCOL is deliberately the smallest thing that could work, because
the whole point is that a half-finished port can run it. Your player is a
command; the runner substitutes two placeholders and runs it once per scene:

    {cart}   path to the cart folder to run
    {out}    path your player writes the frame to

Write EITHER a 76800-byte raw dump of the framebuffer (one byte per pixel,
palette indices, row-major from the top-left) OR an 8-bit indexed PNG. The raw
form exists so a C or firmware implementation needs no image library at all --
`fwrite(framebuffer, 1, 320*240, f)` is a conforming adapter.

Example:

    python3 conformance/run.py --player "./build/moyplay --headless --frames 2 \\
        --dump {out} {cart}"

Exit status is 0 only if every core scene matches. SPEC.md 6.1 scenes are
reported and never counted -- SPEC.md 11 excludes them until 6.1 settles.
"""

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import moycore                                     # noqa: E402
from moycore import png as _png                     # noqa: E402
from conformance import scenes, trace               # noqa: E402

GOLDEN = os.path.join(HERE, "golden")
CARTS = os.path.join(HERE, "carts")
FRAME_BYTES = moycore.WIDTH * moycore.HEIGHT


def load_golden(name):
    path = os.path.join(GOLDEN, name + ".png")
    w, h, px = _png.read_rgb(path)
    if (w, h) != (moycore.WIDTH, moycore.HEIGHT):
        raise SystemExit("golden %s is %dx%d, expected %dx%d"
                         % (name, w, h, moycore.WIDTH, moycore.HEIGHT))
    # Goldens are indexed PNGs; read_rgb resolves through PLTE, so map back.
    index_of = {}
    pal = moycore.palette.MOY64
    for i in range(len(pal)):
        index_of.setdefault(tuple(pal[i]), i)
    out = bytearray(len(px))
    for i in range(len(px)):
        out[i] = index_of.get(px[i], 0)
    return bytes(out)


def render_moycore(name, fn):
    """The built-in adapter: replay the scene's TRACE, not the scene function.

    Through the trace on purpose -- that is the artifact every other
    implementation consumes, so the self-test exercises the same path they do
    rather than a shortcut only Python has."""
    path = os.path.join(HERE, "traces", name + ".json")
    f = open(path)
    try:
        calls = json.load(f)
    finally:
        f.close()
    sheet = moycore.SpriteSheet()
    tilemap = moycore.TileMap(20, 15)
    scenes._fill_sheet(sheet)
    scenes._fill_map(tilemap)
    canvas = moycore.Canvas()
    trace.replay(calls, canvas, sheet, tilemap)
    return bytes(canvas.buf)


def render_external(command, name):
    cart = os.path.join(CARTS, name + ".moy")
    fd, out = tempfile.mkstemp(suffix=".out")
    os.close(fd)
    try:
        cmd = command.replace("{cart}", cart).replace("{out}", out)
        proc = subprocess.run(cmd, shell=True, capture_output=True)
        if proc.returncode != 0:
            return None, "player exited %d: %s" % (
                proc.returncode, proc.stderr.decode("utf-8", "replace").strip()[:400])
        if not os.path.exists(out) or os.path.getsize(out) == 0:
            return None, "player wrote nothing to {out}"
        f = open(out, "rb")
        try:
            blob = f.read()
        finally:
            f.close()
        if len(blob) == FRAME_BYTES:
            return blob, None
        if blob[:8] == b"\x89PNG\r\n\x1a\n":
            w, h, px = _png.read_rgb(out)
            if (w, h) != (moycore.WIDTH, moycore.HEIGHT):
                return None, "player frame is %dx%d, expected %dx%d" % (
                    w, h, moycore.WIDTH, moycore.HEIGHT)
            pal = moycore.palette.MOY64
            index_of = {}
            for i in range(len(pal)):
                index_of.setdefault(tuple(pal[i]), i)
            buf = bytearray(len(px))
            unknown = 0
            for i in range(len(px)):
                v = index_of.get(px[i])
                if v is None:
                    unknown += 1
                    v = _png.nearest_index(px[i], pal)
                buf[i] = v
            if unknown:
                return bytes(buf), ("note: %d pixels were not exact palette "
                                    "colours and were snapped to the nearest" % unknown)
            return bytes(buf), None
        return None, ("player wrote %d bytes -- expected a %d-byte raw frame or an "
                      "indexed PNG" % (len(blob), FRAME_BYTES))
    finally:
        if os.path.exists(out):
            os.remove(out)


def compare(golden, got):
    """(differing pixel count, first (x, y, golden, got)) or (0, None)."""
    n = min(len(golden), len(got))
    count = 0
    first = None
    for i in range(n):
        if golden[i] != got[i]:
            count += 1
            if first is None:
                first = (i % moycore.WIDTH, i // moycore.WIDTH, golden[i], got[i])
    return count, first


def write_diff(path, golden, got):
    """A diff frame: matching pixels dimmed to black, differences in magenta on
    the golden's own colours, so a failure is a picture of WHERE."""
    out = bytearray(len(golden))
    for i in range(len(golden)):
        out[i] = 14 if golden[i] != got[i] else 0
    _png.write_indexed(path, moycore.WIDTH, moycore.HEIGHT, out,
                       moycore.palette.MOY64)


def main(argv):
    player = None
    diff_dir = None
    if "--player" in argv:
        player = argv[argv.index("--player") + 1]
    if "--diff" in argv:
        diff_dir = argv[argv.index("--diff") + 1]
        if not os.path.isdir(diff_dir):
            os.makedirs(diff_dir)

    if not os.path.isdir(GOLDEN) or not os.path.exists(os.path.join(GOLDEN, "hashes.json")):
        raise SystemExit("no goldens; run: python3 conformance/build.py")

    label = player if player else "moycore (built-in)"
    print("conformance: %s" % label)
    print("             %d scenes, %d in core\n"
          % (len(scenes.SCENES), len(scenes.core_scenes())))

    core_fail = 0
    core_total = 0
    for name, fn in scenes.SCENES:
        excluded = name in scenes.EXCLUDED
        golden = load_golden(name)
        if player:
            got, err = render_external(player, name)
        else:
            got, err = render_moycore(name, fn), None
        if got is None:
            print("  ERROR %-12s %s" % (name, err))
            if not excluded:
                core_fail += 1
                core_total += 1
            continue
        count, first = compare(golden, got)
        tag = "  (SPEC.md 6.1, not counted)" if excluded else ""
        if count == 0:
            print("  ok    %-12s%s" % (name, tag))
        else:
            pct = 100.0 * count / FRAME_BYTES
            print("  FAIL  %-12s %d pixels differ (%.2f%%); first at (%d, %d) "
                  "golden=%d yours=%d%s"
                  % (name, count, pct, first[0], first[1], first[2], first[3], tag))
            if diff_dir:
                write_diff(os.path.join(diff_dir, name + ".diff.png"), golden, got)
            if not excluded:
                core_fail += 1
        if err:
            print("        " + err)
        if not excluded:
            core_total += 1

    print()
    if core_fail:
        print("%d of %d core scenes differ -- NOT conforming." % (core_fail, core_total))
        if diff_dir:
            print("diff frames written to %s (magenta = differing pixel)" % diff_dir)
        return 1
    print("all %d core scenes pixel-identical." % core_total)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
