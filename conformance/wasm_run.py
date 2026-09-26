#!/usr/bin/env python3
"""Compiled-cart conformance: every scene on every host, one frame for all.

    python3 conformance/wasm_run.py                   # every host found here
    python3 conformance/wasm_run.py --hosts harness,desktop,browser
    python3 conformance/wasm_run.py --player "CMD"    # one player
    python3 conformance/wasm_run.py --build           # re-render the goldens

The scenes are runtime "wasm" carts under conformance/wasm/, one per import
only this binding has (blit, blit565, read, target) plus `verbs`, the ordinary
verbs through it, `primitives` and the five `layer_*` scenes, SPEC.md 11's
scenes of those names as compiled carts, and `trap`, a trap in the second
frame. Their goldens are RGB565 frames (proposals/wasm-runtime.md,
Determinism), rendered by the twins in wasm_scenes.py, and stored as PNGs
whose channels are each word's bits repeated, so the file is a picture and
reduces back to the word exactly.

THE PLAYER PROTOCOL is SPEC.md 11's, for a compiled cart. Your player is a
command with {cart} and {out} in it; for each cart it runs the cart's ticks
(two, with dt 1/30, the clock stopped and nothing pressed) and writes the last
frame the cart finished to {out}: W x H RGB565 words, little-endian, row-major.
It exits 0 when the cart ran. When a tick traps it exits non-zero and {out}
holds the last whole frame -- never the one the trap interrupted. When the cart
is refused -- its module's shape, or more memory than the player gives a cart
-- it exits non-zero and writes nothing.

The hosts this repository has, each found when it is built:

    harness   libmoy/build/wasm_test play      (make -C libmoy wasm-test)
    desktop   libmoy/build/moy-play --dump     (make -C libmoy play)
    browser   node libmoy/port/wasm/conform.mjs  (runner/, and node)

Every host must match every golden, which makes their frames identical to each
other's; the CRC32 of each frame is printed so a failure says which side moved.
--hosts names the ones that must be present; without it a missing host is
reported and skipped. Exit status is 0 only if every host ran clean.
"""

import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import wat                                         # noqa: E402
from moycore import check as _check                # noqa: E402
from moycore import pack as _pack                  # noqa: E402
from moycore import png as _png                    # noqa: E402
from conformance import wasm_scenes as ws          # noqa: E402

SCENES = os.path.join(HERE, "wasm")
GOLDEN = os.path.join(SCENES, "golden")
FRAME_BYTES = ws.W * ws.H * 2


# -- goldens ----------------------------------------------------------------

def write_png(path, words):
    raw = bytearray()
    for y in range(ws.H):
        raw.append(0)
        for v in words[y * ws.W:(y + 1) * ws.W]:
            r, g, b = v >> 11, (v >> 5) & 63, v & 31
            raw += bytes(((r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)))

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n"
                + chunk(b"IHDR", struct.pack(">IIBBBBB", ws.W, ws.H, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
                + chunk(b"IEND", b""))


def read_golden(name):
    w, h, px = _png.read_rgb(os.path.join(GOLDEN, name + ".png"))
    if (w, h) != (ws.W, ws.H):
        raise SystemExit("golden %s is %dx%d" % (name, w, h))
    return ws.to_bytes([((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3) for r, g, b in px])


def crc(blob):
    return "%08x" % (zlib.crc32(blob) & 0xFFFFFFFF)


def build():
    """The generated scenes' modules from their calls, then every golden from
    its twin."""
    for name, (calls, source, note, blit_first) in sorted(ws.GENERATED.items()):
        with open(os.path.join(SCENES, name + ".moy", "main.wat"), "w",
                  encoding="utf-8", newline="\n") as f:
            f.write(ws.module_wat(calls(), source, note, blit_first))
    if not os.path.isdir(GOLDEN):
        os.makedirs(GOLDEN)
    hashes = {"about": "proposals/wasm-runtime.md's compiled-cart scenes: each golden "
                       "is the RGB565 frame, little-endian, whose sha256 and CRC32 are "
                       "below; the PNG beside it is that frame with each channel's bits "
                       "repeated. Written by conformance/wasm_run.py --build.",
              "frames": ws.FRAMES, "scenes": {}}
    for name, twin in ws.SCENES:
        words = twin()
        blob = ws.to_bytes(words)
        write_png(os.path.join(GOLDEN, name + ".png"), words)
        if read_golden(name) != blob:
            raise SystemExit("golden %s does not read back as it was written" % name)
        hashes["scenes"][name] = {"sha256": hashlib.sha256(blob).hexdigest(),
                                  "crc32": crc(blob), "traps": name in ws.TRAPS}
        print("  wrote %-10s crc32 %s" % (name, crc(blob)))
    with open(os.path.join(GOLDEN, "hashes.json"), "w", encoding="utf-8",
              newline="\n") as f:
        json.dump(hashes, f, indent=2, sort_keys=True)
        f.write("\n")


# -- hosts ------------------------------------------------------------------

def hosts_here():
    """name -> command template, for every host built in this tree."""
    found = {}
    harness = os.path.join(ROOT, "libmoy", "build", "wasm_test")
    if os.path.isfile(harness):
        found["harness"] = '"%s" play {cart} {out}' % harness
    for exe in ("moy-play", "moy-play.exe"):
        desk = os.path.join(ROOT, "libmoy", "build", exe)
        if os.path.isfile(desk):
            try:
                rts = subprocess.run([desk, "--runtimes"], capture_output=True,
                                     text=True, timeout=30).stdout.split()
            except (OSError, subprocess.SubprocessError):
                rts = []
            if "wasm" in rts:
                found["desktop"] = '"%s" {cart} --dump {out}' % desk
            break
    if shutil.which("node") and os.path.isfile(os.path.join(ROOT, "runner", "moy.mjs")):
        found["browser"] = 'node "%s" {cart} {out}' % os.path.join(
            ROOT, "libmoy", "port", "wasm", "conform.mjs")
    return found


def play(command, cart):
    """(exit status, the frame written or None, stderr)."""
    fd, out = tempfile.mkstemp(suffix=".bin")
    os.close(fd)
    os.remove(out)
    try:
        cmd = command.replace("{cart}", '"%s"' % cart).replace("{out}", '"%s"' % out)
        p = subprocess.run(cmd, shell=True, capture_output=True, timeout=300)
        frame = None
        if os.path.exists(out) and os.path.getsize(out):
            with open(out, "rb") as f:
                frame = f.read()
        return p.returncode, frame, p.stderr.decode("utf-8", "replace").strip()
    finally:
        if os.path.exists(out):
            os.remove(out)


def first_diff(want, got):
    for i in range(0, min(len(want), len(got)), 2):
        if want[i:i + 2] != got[i:i + 2]:
            n = i // 2
            return "first at (%d, %d)" % (n % ws.W, n // ws.W)
    return ""


def run_host(label, command, scratch, goldens):
    print("%s: %s" % (label, command))
    bad = 0
    for name, _ in ws.SCENES:
        cart = os.path.join(scratch, name + ".moy")
        rc, frame, err = play(command, cart)
        want = goldens[name]
        traps = name in ws.TRAPS
        if frame is None:
            print("  FAIL  %-10s no frame (exit %d): %s" % (name, rc, err[:200]))
            bad += 1
        elif len(frame) != FRAME_BYTES:
            print("  FAIL  %-10s a %d-byte frame, not %d" % (name, len(frame), FRAME_BYTES))
            bad += 1
        elif frame != want:
            diff = sum(1 for i in range(0, FRAME_BYTES, 2) if frame[i:i + 2] != want[i:i + 2])
            print("  FAIL  %-10s crc32 %s, golden %s: %d pixels differ, %s"
                  % (name, crc(frame), crc(want), diff, first_diff(want, frame)))
            bad += 1
        elif traps and rc == 0:
            print("  FAIL  %-10s trapped, and the player exited 0" % name)
            bad += 1
        elif not traps and rc != 0:
            print("  FAIL  %-10s exited %d: %s" % (name, rc, err[:200]))
            bad += 1
        else:
            print("  ok    %-10s crc32 %s%s" % (name, crc(frame),
                                              "  (trapped; the last whole frame)" if traps else ""))
    for rel, why in ws.REFUSED:
        cart = os.path.join(scratch, os.path.basename(rel))
        rc, frame, err = play(command, cart)
        name = os.path.basename(rel)[:-4]
        if rc == 0 or frame is not None:
            print("  FAIL  %-15s should be refused (%s): exit %d, %s"
                  % (name, why, rc, "a frame written" if frame else "no frame"))
            bad += 1
        else:
            print("  ok    %-15s refused: %s" % (name, err.splitlines()[-1][:110] if err else "(no message)"))
    return bad


def main(argv):
    if "--build" in argv:
        print("wasm conformance: building the goldens from wasm_scenes.py")
        build()
        return 0

    goldens = {}
    manifest = json.load(open(os.path.join(GOLDEN, "hashes.json"), encoding="utf-8"))
    for name, _ in ws.SCENES:
        goldens[name] = read_golden(name)
        rec = manifest["scenes"].get(name)
        if not rec or rec["sha256"] != hashlib.sha256(goldens[name]).hexdigest():
            raise SystemExit("golden %s does not match hashes.json; "
                             "run conformance/wasm_run.py --build" % name)

    if "--player" in argv:
        hosts = {"player": argv[argv.index("--player") + 1]}
        required = []
    else:
        hosts = hosts_here()
        required = []
        if "--hosts" in argv:
            required = argv[argv.index("--hosts") + 1].split(",")
        for want in required:
            if want not in hosts:
                print("wasm conformance: the %s host is not built here" % want)
                return 1

    scratch = tempfile.mkdtemp(prefix="moy-wasm-conform-")
    try:
        for name, _ in ws.SCENES:
            wat.build_cart(os.path.join(SCENES, name + ".moy"),
                           os.path.join(scratch, name + ".moy"))
        for rel, _ in ws.REFUSED:
            wat.build_cart(os.path.join(ROOT, rel),
                           os.path.join(scratch, os.path.basename(rel)))
        # A scene is a conforming cart: `moy check` finds nothing wrong with it.
        for name, _ in ws.SCENES:
            files = _pack.read_folder(os.path.join(scratch, name + ".moy"))
            errors = [m for lvl, _, m in _check.check_wasm_files(files) if lvl == "error"]
            if errors:
                print("wasm conformance: the %s scene is not a conforming cart: %s"
                      % (name, errors[0]))
                return 1
        print("wasm conformance: %d scenes, %d refusals, %d frames each\n"
              % (len(ws.SCENES), len(ws.REFUSED), ws.FRAMES))
        bad = 0
        for label in ("harness", "desktop", "browser", "player"):
            if label in hosts:
                bad += run_host(label, hosts[label], scratch, goldens)
        missing = [h for h in ("harness", "desktop", "browser")
                   if h not in hosts and "player" not in hosts]
        for h in missing:
            print("%s: not built here, skipped" % h)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    if bad:
        print("\n%d failure%s." % (bad, "" if bad == 1 else "s"))
        return 1
    ran = [h for h in hosts]
    print("\nevery scene identical on %s; every refusal refused." % ", ".join(ran))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
