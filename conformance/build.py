"""Build the conformance suite: traces, carts, golden frames, hashes.

    python3 conformance/build.py

Produces, for every scene:

    conformance/carts/<name>.moy/     a real moy cart any host can run
    conformance/traces/<name>.json    the portable verb trace
    conformance/golden/<name>.png     the golden frame (indexed PNG)
    conformance/golden/hashes.json    sha256 per frame + the suite manifest

Three self-checks run before anything is written, because a golden nobody
verified is just a record of what the code did that day:

  1. The recorded trace, replayed, must reproduce the scene's own framebuffer.
     Otherwise the cart and the golden are of different pictures.
  2. Every verb in every trace must be in trace.ARITY, so a port that
     implements the published list can run the whole suite.
  3. The generated carts must load through moycore.load_cart -- if the suite's
     own carts do not pass the loader, the suite is not testing what it claims.

PROVENANCE: these goldens are rendered by moycore, and the WebAssembly player
SPEC.md 11 names as the tiebreaker agrees with them on every scene -- along with
libmoy, the reference console, and an ESP32-P4. See the README, which is also
where the LIMITS of that agreement are recorded: all but the board share one
lineage.
"""

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import moycore                                          # noqa: E402
from moycore import png as _png                         # noqa: E402
from conformance import scenes, trace                   # noqa: E402

CARTS = os.path.join(HERE, "carts")
TRACES = os.path.join(HERE, "traces")
GOLDEN = os.path.join(HERE, "golden")

NOTES = {
    "primitives": "Every core drawing verb (SPEC.md 6) at a size where the\n"
                  "rasterization is visible, plus the degenerate cases: a 1x1\n"
                  "rect, r=0 and r=1 circles, zero-size rects.",
    "edges": "Clipping. Every shape hangs off an edge; a host that clamps\n"
             "instead of clipping, or wraps a row, fails here and nowhere else.",
    "text": "The whole printable range (SPEC.md 6), then bytes outside it,\n"
            "which must draw nothing and still advance 8px.",
    "text_bytes": "Bytes outside 0x20-0x7F, which draw nothing and still advance\n"
                  "8px. SPEC.md 6: print walks BYTES, so a two-byte UTF-8\n"
                  "character takes two cells, not one.",
    "camera_clip": "camera and clip TOGETHER. clip is screen space, applied\n"
                   "after the camera offset -- an implementation that clips in\n"
                   "world space passes both features separately and fails this.",
    "pal_palt": "Draw-time remap and sprite transparency, including the case\n"
                "where both are active. pal must not touch pixels already drawn.",
    "sprites": "Flips, integer scales, colorkeys, out-of-range tile ids, and\n"
               "sprites under camera and clip.",
    "tilemap": "map() regions, screen offsets, scale, colorkey, camera, clip,\n"
               "and a region starting outside the map.",
    "oval": "oval and ovalb (SPEC.md 6): round, wide, tall and flat boxes, the\n"
            "1x1/2x2/3x3 sizes, zero and negative sizes, edges, camera, clip\n"
            "and pal, and the outline drawn over its own fill.",
    "fillp": "The fill pattern (SPEC.md 6): a set bit is a hole, a hole takes\n"
             "the second colour or nothing, the pattern is anchored to the\n"
             "SCREEN through camera and clip, every shape verb honours it and\n"
             "pix, print, sprites and the map do not.",
    "sheet": "sset (SPEC.md 7.1): a sheet write is what spr, sspr and map draw\n"
             "next; the index is masked to 0-15; writes off the sheet are\n"
             "dropped.",
    "flags": "Tile flags (SPEC.md 3.5, 7.1, 7.2): map(..., layers) draws only\n"
             "the cells whose tile shares a flag bit with the mask; fset\n"
             "changes that on the next map(); a mask against no flags draws\n"
             "nothing. The scene restores what it edits first.",
    "screen_pal": "The screen palette (SPEC.md 6, 12.1): pal(c0, c1, 1) moves\n"
                  "pixels ALREADY drawn, chains after the draw palette, and\n"
                  "pal() resets both. The golden is the frame as shown.",
    "provisional": "SPEC.md 6.1 verbs. NOT part of conformance -- SPEC.md 11\n"
                   "excludes 6.1 until its promotion gates clear. Kept so the\n"
                   "golden already exists when they do.",
    "provisional_tline": "SPEC.md 6.1 tline: line()'s pixels, texture-stepped\n"
                         "across the map in 16.16 fixed point. Excluded like\n"
                         "`provisional`, and separate so a host with tri/sspr\n"
                         "but no tline fails one scene, not both.",
}


def _mkdir(path):
    if not os.path.isdir(path):
        os.makedirs(path)


def _write(path, blob):
    mode = "wb" if isinstance(blob, (bytes, bytearray)) else "w"
    f = open(path, mode, **({} if mode == "wb" else {"encoding": "utf-8", "newline": "\n"}))
    try:
        f.write(blob)
    finally:
        f.close()


def build_assets():
    """The sheet, map and tile flags every conformance cart shares."""
    sheet = moycore.SpriteSheet()
    tilemap = moycore.TileMap(20, 15)
    flags = bytearray(512)
    scenes._fill_sheet(sheet)
    scenes._fill_map(tilemap)
    scenes._fill_flags(flags)
    return sheet, tilemap, flags


def main():
    _mkdir(CARTS); _mkdir(TRACES); _mkdir(GOLDEN)
    sheet, tilemap, flags = build_assets()
    sheet_hex = sheet.to_hex()
    map_hex = tilemap.to_hex()
    flags_hex = moycore.cart.flags_to_hex(flags)

    manifest_scenes = []
    problems = []

    for name, fn in scenes.SCENES:
        # 1. Run the scene, recording it.
        s, t, fl = build_assets()
        direct = moycore.Canvas()
        rec = trace.RecordingCanvas(direct, s, t, fl)
        fn(rec, s, t)
        calls = rec.calls

        # 2. Replay the trace into a fresh canvas and demand the same pixels.
        s2, t2, fl2 = build_assets()
        replayed = moycore.Canvas()
        trace.replay(calls, replayed, s2, t2, fl2)
        if replayed.present() != direct.present():
            problems.append("%s: the recorded trace does not reproduce the scene" % name)
            continue

        # 3. Every verb must be in the published arity table.
        for call in calls:
            verb = call[0]
            if verb not in trace.ARITY:
                problems.append("%s: verb %r is not in trace.ARITY" % (name, verb))
            elif (len(call) - 1) not in trace.ARITY[verb]:
                problems.append("%s: %s takes %s args, trace has %d"
                                % (name, verb, trace.ARITY[verb], len(call) - 1))

        _write(os.path.join(TRACES, name + ".json"),
               json.dumps(calls, separators=(",", ":")) + "\n")

        cart_dir = os.path.join(CARTS, name + ".moy")
        _mkdir(cart_dir)
        cart_manifest = {
            "format": "moy-1",
            "title": "conformance: " + name,
            "author": "moy",
            "version": 1,
            "main": "main.lua",
            "fps": 30,
            "input": ["buttons"],
        }
        _write(os.path.join(cart_dir, "manifest.json"),
               json.dumps(cart_manifest, indent=2) + "\n")
        _write(os.path.join(cart_dir, "main.lua"),
               trace.to_lua(calls, name, NOTES.get(name, "")))
        _write(os.path.join(cart_dir, "sprites.moygfx"), sheet_hex + "\n")
        _write(os.path.join(cart_dir, "map.moymap"), map_hex + "\n")
        _write(os.path.join(cart_dir, "flags.moyflags"), flags_hex)

        # 4. The generated cart must load.
        try:
            moycore.load_cart(cart_dir)
        except Exception as exc:
            problems.append("%s: generated cart does not load: %s" % (name, exc))

        indexed = direct.present()      # a golden is the frame as SHOWN
        _png.write_indexed(os.path.join(GOLDEN, name + ".png"),
                           direct.w, direct.h, indexed, direct.palette)
        manifest_scenes.append({
            "name": name,
            "core": name not in scenes.EXCLUDED,
            "calls": len(calls),
            "frame_sha256": hashlib.sha256(indexed).hexdigest(),
            "note": NOTES.get(name, ""),
        })
        print("  %-12s %4d calls  %s  %s"
              % (name, len(calls),
                 manifest_scenes[-1]["frame_sha256"][:16],
                 "" if name not in scenes.EXCLUDED else "(excluded)"))

    if problems:
        print("\nBUILD FAILED:")
        for p in problems:
            print("  " + p)
        return 1

    _write(os.path.join(GOLDEN, "hashes.json"), json.dumps({
        "suite": "moy core conformance",
        "spec": "0.1",
        "raster": {"w": moycore.WIDTH, "h": moycore.HEIGHT},
        "generated_by": "moycore %s" % moycore.__version__,
        "provenance": (
            "Rendered by moycore. Confirmed pixel-identical on all core scenes "
            "by the reference console's own rasterizer (conformance/parity.py), "
            "by libmoy and the WebAssembly player built from it (the tiebreaker "
            "SPEC.md 11 names), and by an ESP32-P4 over serial. Note that ALL "
            "FIVE now share moycore's lineage -- the board ran a hand "
            "transcription until 2026-08-07 and now calls libmoy too. See "
            "conformance/README.md, 'The independent check, and its loss'."),
        "scenes": manifest_scenes,
    }, indent=2) + "\n")
    print("\n%d scenes built (%d in core conformance)."
          % (len(manifest_scenes),
             sum(1 for s in manifest_scenes if s["core"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
