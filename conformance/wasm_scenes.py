"""The compiled-cart scenes (SPEC.md 16), and what each must draw.

Every scene is a runtime "wasm" cart under conformance/wasm/<name>.moy, its
module committed as WAT source (tools/wat.py assembles it), and a Python twin
here that renders the frame SPEC.md 16's rules say it draws: the blit's
palette and bytes applied by hand, and every ordinary verb drawn by moycore,
the raster the suite's goldens come from. `conformance/wasm_run.py --build`
writes the goldens from these twins and `conformance/wasm_run.py` holds every
host to them.

A wasm golden is an RGB565 frame (SPEC.md 16.11): W x H
little-endian words, each colour's high bits, so a palette blit's 256 colours
and a blit565 frame are both representable and a verb's colour is its palette
entry reduced the same way.

The generated scenes are written as data rather than WAT, and module_wat()
turns the data into the module, so the cart and its twin cannot drift. `verbs`
is VERBS, a list of calls in the import table's own forms, which verbs()
replays through moycore. `primitives` and the five `layer_*` scenes are the
SPEC.md 11 scenes of those names, each recorded trace made into a compiled
cart: its golden is that scene's golden, every index reduced to the word its
palette entry is.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import moycore                          # noqa: E402
from moycore import palette as _palette  # noqa: E402

W, H = 320, 240
# Every scene runs this many ticks on every host, and a twin draws the frame
# the last of them leaves.
FRAMES = 2
UNDRAWN = 0xFF                          # no palette index is 255
SCENES_DIR = os.path.join(HERE, "wasm")


def rgb565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


MOY565 = [rgb565(*_palette.MOY64[i]) for i in range(64)]


def blank_canvas():
    """A canvas that starts out holding nothing any verb writes, so what the
    verbs drew can be laid over a blitted frame."""
    c = moycore.Canvas(W, H)
    c.buf[:] = bytes((UNDRAWN,)) * (W * H)
    return c


def over(words, canvas):
    """`words` with every pixel a verb drew replaced by its colour."""
    out = list(words)
    for i, v in enumerate(canvas.buf):
        if v != UNDRAWN:
            out[i] = MOY565[v]
    return out


def indexed_frame(index_of, pal565):
    """A blit's frame: index_of(x, y) through a 256-entry table of words."""
    return [pal565[index_of(i % W, i // W) & 255] for i in range(W * H)]


CART_PALETTE = [MOY565[i & 63] for i in range(256)]   # blit's pal 0


def to_bytes(words):
    out = bytearray(len(words) * 2)
    for i, v in enumerate(words):
        out[2 * i] = v & 0xFF
        out[2 * i + 1] = v >> 8
    return bytes(out)


# -- the hand-written scenes ------------------------------------------------

def blit():
    pal = [rgb565(i, (i * 37) & 255, 255 - i) for i in range(256)]
    words = indexed_frame(lambda x, y: 3 * x + 5 * y, pal)
    c = blank_canvas()
    c.camera(6, 4)
    c.clip(0, 0, 100, 100)
    c.pal(8, 12)
    c.rect(6, 4, 120, 12, 8)
    c.print("256 COLOURS", 8, 6, 7)
    return over(words, c)


def blit565():
    words = []
    for i in range(W * H):
        x, y = i % W, i // W
        words.append(((x // 10) << 11) | (((63 * y) // 239) << 5) | ((x + y) & 31))
    c = blank_canvas()
    c.circb(160, 120, 40, 7)
    c.print("RGB565", 136, 116, 7)
    return over(words, c)


def _read(files, name, offset, n):
    """SPEC.md 16.6's read, from the rule: (answer, bytes)."""
    segs = name.split("/")
    if (not name or "\\" in name or "\0" in name
            or any(s in ("", ".", "..") for s in segs) or name not in files):
        return 0, b""
    data = files[name]
    if offset >= len(data):
        return 0, b""
    rest = data[offset:]
    if n == 0:
        return len(rest), b""
    got = rest[:n]
    return len(got), got


def read():
    folder = os.path.join(SCENES_DIR, "read.moy")
    files = {}
    for dirpath, _, names in os.walk(folder):
        for fn in names:
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, folder).replace(os.sep, "/")
            if rel != "main.wat":
                with open(p, "rb") as f:
                    files[rel] = f.read()
    asks = [("data.bin", 0, 0), ("data.bin", 0, 256), ("data.bin", 250, 16),
            ("data.bin", 100, 0), ("data.bin", 300, 16), ("data.bin", 256, 16),
            ("nothing.bin", 0, 16), ("../read.moy/data.bin", 0, 16),
            ("./data.bin", 0, 16), ("sub//note.txt", 0, 16),
            ("sub\\note.txt", 0, 16), ("sub/note.txt", 0, 32),
            ("/data.bin", 0, 16), ("sub", 0, 0), ("data.bin", 255, 1)]
    answers = [_read(files, *a) for a in asks]
    data = answers[1][1]
    words = indexed_frame(
        lambda x, y: data[((x >> 2) & 15) | (((y >> 2) & 15) << 4)], CART_PALETTE)
    c = blank_canvas()
    for k, (v, _) in enumerate(answers):
        h = (v & 63) + 1
        c.rect(4 + k * 21, 236 - h, 18, h, 8 + (v >> 6))
    for j, b in enumerate(answers[2][1]):
        c.rect(8 + j * 10, 150, 8, 8, b)
    c.rect(72, 150, 8, 8, answers[14][1][0])
    c.print(answers[11][1], 8, 164, 7)
    return over(words, c)


def target():
    screen = moycore.Canvas(W, H)
    layer = screen.new_layer(W, H)
    layer.cls(2)
    layer.camera(-10, -10)
    layer.circ(50, 50, 20, 9)
    layer.rectb(0, 0, 100, 60, 11)
    layer.print("LAYER", 20, 90, 7)
    seen = layer.pix(60, 60)
    for _ in range(FRAMES):
        screen.reset_state()
        screen.cls(5)
        layer.pix(0, 0, 14)
        screen.blit_window_from(layer, 0, 0)
        screen.camera(3, 3)
        screen.rect(0, 0, 16, 16, seen)
        screen.camera(0, 0)
        layer.rect(200, 150, 30, 30, 6)
        screen.rect(300, 220, 20, 20, 14)
    return [MOY565[v] for v in screen.buf]


def trap():
    c = moycore.Canvas(W, H)
    c.cls(3)
    c.circ(160, 120, 50, 10)
    return [MOY565[v] for v in c.buf]


SND_RATE, SND_DEPTH = 22050, 2048       # SPEC.md 16.9


def snd():
    """The queue from the rule, with the clock stopped: nothing drains."""
    queued = [0]

    def ask(n):
        room = SND_DEPTH - queued[0]
        if n == 0:
            return room
        got = min(n, room)
        queued[0] += got
        return got

    answers = [ask(0), ask(300), ask(0), ask(2000), ask(0), ask(1), ask(0), ask(0)]
    c = moycore.Canvas(W, H)
    c.cls(1)
    for k, v in enumerate(answers):
        h = (v & 63) + 1
        c.rect(4 + k * 21, 236 - h, 18, h, 8 + (v >> 6))
    return [MOY565[v] for v in c.buf]


def snd_trap():
    c = moycore.Canvas(W, H)
    c.cls(12)
    c.circ(160, 120, 40, 7)
    return [MOY565[v] for v in c.buf]


def par():
    """Eight items of thirty rows each, then a bar per item and one for the
    caller, green where the stack pointer was the one the rule gives."""
    words = []
    for n in range(W * H):
        x, y = n % W, n // W
        i = y // 30
        words.append((((3 * x + 5 * i) & 31) << 11) | (((2 * y + 7 * i) & 63) << 5)
                     | ((x ^ y) & 31))
    c = blank_canvas()
    for k in range(8):
        c.rect(4 + k * 20, 4, 16, 8, 11)
    c.rect(170, 4, 16, 8, 11)
    return over(words, c)


def par_trap():
    """The first frame: four quarters of the rows, item i's in word 8191i + 1."""
    return [(8191 * ((n // W) // 60) + 1) & 0xFFFF for n in range(W * H)]



# -- write: the cart's writable files, over two runs (SPEC.md 16.12) -----------

PATH_MAX, WRITE_MAX = 64, 1048576       # SPEC.md 16.12


def _cart_files(name):
    """{path: bytes} of a scene cart as it ships: every file but its WAT."""
    folder = os.path.join(SCENES_DIR, name + ".moy")
    files = {}
    for dirpath, _, names in os.walk(folder):
        for fn in names:
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, folder).replace(os.sep, "/")
            if rel != "main.wat":
                with open(p, "rb") as f:
                    files[rel] = f.read()
    return files


def _well_formed(path):
    segs = path.split("/")
    return (bool(path) and "\\" not in path and "\0" not in path
            and all(s not in ("", ".", "..") for s in segs))


class _Files:
    """SPEC.md 16.12's rules, from the text: a cart's shipped files, its
    writable entries, and what it has written."""

    def __init__(self, shipped, writable, written=None):
        self.shipped = shipped
        self.entries = [e for e in writable if len(e) <= PATH_MAX and _well_formed(
            e[:-1] if e.endswith("/") else e)]
        self.written = dict(written or {})

    def writable(self, path):
        if len(path) > PATH_MAX or not _well_formed(path):
            return False
        return any(path == e or (e.endswith("/") and path.startswith(e) and path != e)
                   for e in self.entries)

    def read(self, path, n):
        if not _well_formed(path):
            return 0, b""
        data = self.written.get(path) if self.writable(path) else None
        if data is None:
            data = self.shipped.get(path)
        if data is None:
            return 0, b""
        return (len(data), b"") if n == 0 else (min(n, len(data)), data[:n])

    def write(self, path, data):
        if not self.writable(path):
            return -1
        if len(data) > WRITE_MAX:
            return -2
        self.written[path] = bytes(data)
        return 0

    def erase(self, path):
        if not self.writable(path) or path not in self.written:
            return -1
        del self.written[path]
        return 0

    def list(self, prefix, i, n):
        names = sorted(set(self.shipped) | set(self.written),
                       key=lambda p: p.encode("utf-8"))
        names = [p for p in names if p.startswith(prefix)]
        if i >= len(names):
            return -1, b""
        b = names[i].encode("utf-8")
        return len(b), b[:n]


def _write_runs():
    """Both runs of the write scene over one store: (answers, what the cart
    keeps in memory) for each."""
    shipped = _cart_files("write")
    with open(os.path.join(SCENES_DIR, "write.moy", "manifest.json")) as f:
        writable = json.load(f)["writable"]
    store = _Files(shipped, writable)
    slot1 = bytes((i * 7) & 255 for i in range(300))
    runs = []
    for _ in range(2):
        a, mem = [], {}
        a.append(store.read("options.cfg", 0)[0])
        a.append(store.read("saves/slot1.sav", 0)[0])
        listed = []

        def listing():
            for i in range(8):
                v, b = store.list("saves/", i, 24)
                a.append(v)
                listed.append(b)

        if not a[1]:
            a.append(store.write("options.cfg", b"volume=9!"))
            v, mem["options"] = store.read("options.cfg", 32)
            a.append(v)
            for bad in ("readme.txt", "saves", "saves/../readme.txt", "saves//a.sav",
                        "/options.cfg", "saves/" + "a" * 59):
                a.append(store.write(bad, b"deep"[:4] if bad.endswith("a") else b"volume=9!"))
            a.append(store.write("saves/" + "b" * 58, b"deep"))
            a.append(store.write("saves/big.bin", bytes(WRITE_MAX + 1)))
            a.append(store.write("saves/slot1.sav", slot1))
            a.append(store.write("saves/slot2.sav", b""))
            a.append(store.write("saves/sub/deep.sav", b"deep"))
            a.append(store.write("saves/Case.sav", b"C"))
            a.append(store.write("saves/case.sav", b"ca"))
            a.append(store.write("saves/slot0.sav", b"WRITTEN0!"))
            a.append(store.write("saves/tmp.sav", b"d"))
            a.append(store.erase("saves/tmp.sav"))
            a.append(store.erase("saves/tmp.sav"))
            a.append(store.erase("readme.txt"))
            a.append(store.read("saves/tmp.sav", 0)[0])
            a.append(store.read("saves/slot2.sav", 0)[0])
            a.append(store.write("Saves/X.sav", b"deep"))
            a.append(store.list("saves/", 99, 0)[0])
            a.append(store.list("saves/x", 0, 0)[0])
            a.append(store.list("saves/s", 3, 0)[0])
            a.append(store.list("saves/s", 4, 0)[0])
            listing()
            v, mem["slot0"] = store.read("saves/slot0.sav", 16)
            a.append(v)
        else:
            v, mem["slot1"] = store.read("saves/slot1.sav", 300)
            a.append(v)
            v, mem["options"] = store.read("options.cfg", 32)
            a.append(v)
            v, mem["slot0"] = store.read("saves/slot0.sav", 16)
            a.append(v)
            a.append(store.erase("options.cfg"))
            a.append(store.read("options.cfg", 0)[0])
            a.append(store.erase("saves/slot0.sav"))
            v, mem["shipped0"] = store.read("saves/slot0.sav", 16)
            a.append(v)
            a.append(store.erase("saves/sub/deep.sav"))
            a.append(store.read("saves/sub/deep.sav", 0)[0])
            a.append(store.read("saves/Case.sav", 0)[0])
            a.append(store.read("saves/case.sav", 0)[0])
            listing()
            a.append(sum(1 for i in range(300) if mem["slot1"][i:i + 1] != slot1[i:i + 1]))
        runs.append((a, mem, listed))
    return runs


def _write_frame(run):
    a, mem, listed = _write_runs()[run - 1]
    c = moycore.Canvas(W, H)
    c.cls(1)
    c.rect(300, 8, 12, 12, 10 + run)
    for k, v in enumerate(a):
        u = (v + 4) & 0xFFFFFFFF
        h = (u & 63) + 1
        c.rect(4 + k * 8, 236 - h, 6, h, 8 + ((u >> 6) & 31))
    for i, b in enumerate(listed):
        if b:
            c.print(b, 8, 8 + i * 10, 7)

    def nine(key, n=9):
        return (mem.get(key, b"") + bytes(n))[:n]

    c.print(nine("options"), 8, 100, 7)
    c.print(nine("slot0"), 8, 112, 7)
    if run == 2:
        c.print(nine("shipped0", 8), 8, 124, 7)
        for i in range(64):
            c.rect(8 + (i % 32) * 9, 140 + (i // 32) * 9, 8, 8, mem["slot1"][i] & 63)
    return [MOY565[v] for v in c.buf]


def write():
    return _write_frame(1)


def write_again():
    return _write_frame(2)

# -- verbs: every ordinary verb through the binding, as data -----------------

def _tile_pixels():
    """Tiles 1 and 2 of the sheet the scene writes with sset."""
    out = []
    for y in range(8):
        for x in range(8):
            if abs(2 * x - 7) + abs(2 * y - 7) <= 8:
                c1 = 12
            else:
                c1 = 5 if (x + y) % 3 == 0 else 0
            out.append(("sset", 8 + x, y, c1))
            out.append(("sset", 16 + x, y, 3 if ((x >> 1) + (y >> 1)) & 1 else 14))
    return out


# A call is (verb, args...) at the import's own arity: a whole number is an
# i32, a str is the bytes and length a string takes, and a tuple is a call
# whose result is the argument. ("load", addr) reads an i32 the cart holds.
OUT = 4096          # where camera writes its previous offset

VERBS = _tile_pixels() + [
    ("fset", 1, -1, 0x03), ("fset", 2, 0, 1),
    ("mset", 0, 0, 1), ("mset", 1, 0, 2), ("mset", 2, 1, 1), ("mset", 3, 1, 2),
    ("rect", 4, 4, 60, 30, 8),
    ("rectb", 70, 4, 60, 30, 12),
    ("circ", 30, 70, 20, 11),
    ("circb", 90, 70, 20, 14),
    ("oval", 130, 4, 50, 30, 10),
    ("ovalb", 130, 40, 50, 30, 9),
    ("line", 190, 4, 250, 60, 7),
    ("tri", 260, 4, 310, 30, 270, 60, 13),
    ("trib", 190, 70, 250, 90, 200, 110, 15),
    ("pix", 5, 100, 7), ("pix", 6, 101, 7),
    ("print", "VERBS", 10, 110, 7),
    ("camera", 9, 7, 0), ("rect", 0, 120, 20, 10, 3), ("camera", 0, 0, OUT),
    ("rect", 4, 134, 8, 8, ("load", OUT)), ("rect", 14, 134, 8, 8, ("load", OUT + 4)),
    ("clip", 30, 120, 20, 20), ("circ", 40, 130, 15, 2), ("clip", 0, 0, W, H),
    ("pal", 8, 21, 0), ("rect", 60, 120, 20, 10, 8), ("pal", -1, 0, 0),
    ("pal", 7, 25, 1), ("print", "SCREEN", 90, 120, 7), ("pal", -1, 0, 0),
    ("fillp", 0x5A5A, 1), ("rect", 150, 120, 30, 20, 6), ("fillp", 0, -1),
    ("spr", 1, 190, 120, -1, 1, 0),
    ("spr", 2, 200, 120, 0, 2, 1),
    ("palt", 5, 1), ("spr", 1, 220, 120, -1, 1, 3), ("palt", -1, 0),
    ("sspr", 8, 0, 16, 8, 240, 120, 32, 12, -1, 2),
    ("map", 0, 0, 4, 2, 10, 150, -1, 1, 0),
    ("map", 0, 0, 4, 2, 60, 150, -1, 2, 2),
    ("tline", 150, 160, 300, 170, 0, 0, 0x8000, 0x2000, -1),
    ("rect", 280, 200, 12, 12, ("pix", 5, 100, -1)),
    ("rect", 294, 200, 12, 12, ("sget", 10, 2)),
    ("rect", 308, 200, 12, 12, ("mget", 1, 0)),
    ("rect", 280, 214, 12, 12, ("fget", 1, -1)),
    ("rect", 294, 214, 12, 12, ("fget", 2, 0)),
    ("rect", 308, 214, 12, 12, ("flr", -2.5)),
]


def _verbs_frame(x, y):
    return x ^ y


def _replay(calls, c, sheet, tilemap, flags, mem):
    def value(a):
        if isinstance(a, tuple):
            return run(a)
        return a

    def run(call):
        verb, args = call[0], [value(a) for a in call[1:]]
        if verb == "load":
            return mem.get(args[0], 0)
        if verb == "flr":
            import math
            return int(math.floor(args[0]))
        if verb == "pix":
            if args[2] < 0:
                return c.pix(args[0], args[1])
            c.pix(*args)
        elif verb in ("cls", "line", "rect", "rectb", "circ", "circb", "oval",
                      "ovalb", "tri", "trib"):
            getattr(c, verb)(*args)
        elif verb == "print":
            c.print(args[0].encode("ascii"), *args[1:])
        elif verb == "camera":
            prev = c.camera(args[0], args[1])
            if args[2]:
                mem[args[2]], mem[args[2] + 4] = prev
        elif verb == "clip":
            c.clip(*args)
        elif verb == "pal":
            c.pal() if args[0] < 0 else c.pal(*args)
        elif verb == "palt":
            c.palt() if args[0] < 0 else c.palt(args[0], args[1] != 0)
        elif verb == "fillp":
            c.fillp(args[0], args[1])
        elif verb == "spr":
            c.spr_tile(sheet, *args)
        elif verb == "sspr":
            c.sspr(sheet, *args)
        elif verb == "map":
            c.map(tilemap, sheet, *args, flags=flags)
        elif verb == "tline":
            c.tline(tilemap, sheet, *args)
        elif verb == "sset":
            sheet.pset(*args)
        elif verb == "sget":
            return sheet.pget(*args)
        elif verb == "mset":
            tilemap.mset(*args)
        elif verb == "mget":
            return tilemap.mget(*args)
        elif verb == "fset":
            n, b, v = args
            if b < 0:
                flags[n] = v & 0xFF
            elif v:
                flags[n] |= 1 << (b & 7)
            else:
                flags[n] &= ~(1 << (b & 7)) & 0xFF
        elif verb == "fget":
            n, b = args
            return flags[n] if b < 0 else (flags[n] >> (b & 7)) & 1
        else:
            raise ValueError("no twin for %r" % verb)
        return 0

    for call in calls:
        run(call)


def verbs():
    words = indexed_frame(_verbs_frame, CART_PALETTE)
    c = blank_canvas()
    _replay(VERBS, c, moycore.SpriteSheet(), moycore.TileMap(20, 15),
            bytearray(512), {})
    return over(words, c)


def trace_golden(name):
    """SPEC.md 11's golden for scene `name`, reduced to RGB565."""
    from conformance import run as _run
    return [MOY565[v] for v in _run.load_golden(name)]


def trace_calls(name):
    """Scene `name`'s trace in the import table's own forms: each short Lua
    form spelled out with the sentinel wasm-imports.json gives it."""
    with open(os.path.join(HERE, "traces", name + ".json")) as f:
        calls = json.load(f)
    size = {0: (W, H)}
    target = 0
    out = []
    for c in calls:
        verb = c[0]
        a = [int(v) if isinstance(v, bool) else v for v in c[1:]]
        if verb == "make_layer":
            size[a[0]] = (a[1], a[2])
        elif verb == "target":
            target = a[0]
        elif verb == "pal":
            a = a + [0] * (3 - len(a)) if a else [-1, 0, 0]
        elif verb == "palt":
            a = a or [-1, 0]
        elif verb == "clip":
            a = a or [0, 0, size[target][0], size[target][1]]
        elif verb == "camera":
            a = (a or [0, 0]) + [0]
        elif verb == "fillp":
            a = a or [0, -1]
        elif verb == "map" and len(a) == 8:
            a = a + [0]
        elif verb == "fset" and len(a) == 2:
            a = [a[0], -1, a[1]]
        elif verb == "print" and not isinstance(a[0], str):
            raise ValueError("%s: a compiled scene's text is ASCII" % name)
        out.append(tuple([verb] + a))
    return out


def primitives():
    return trace_golden("primitives")


def primitives_calls():
    return trace_calls("primitives")


VERBS_NOTE = [
    "Every ordinary verb through the wasm binding, at the import table's own",
    "arity -- sentinels for the Lua forms, an out pointer for camera's",
    "previous offset, the read-backs feeding colours -- over a frame blitted",
    "through the cart's own palette, whose indices run past 63 and wrap. The",
    "sheet and map are written by the scene itself, so no host needs its",
    "asset files.",
]

PRIMITIVES_NOTE = [
    "SPEC.md 11's `primitives` scene (conformance/traces/primitives.json) as a",
    "compiled cart: the same calls, through the wasm binding, held to that",
    "scene's golden reduced to RGB565.",
]

# SPEC.md 11's layer scenes, each a draw_layer whose window the camera clamp
# (SPEC.md 6) keeps inside the layer.
LAYER_SCENES = ("layer_left", "layer_right", "layer_top", "layer_bottom",
                "layer_small")


def layer_note(name):
    return [
        "SPEC.md 11's `%s` scene (conformance/traces/%s.json) as a" % (name, name),
        "compiled cart: its layer made in _init, drawn into through `target`,",
        "composited with draw_layer, and held to that scene's golden reduced",
        "to RGB565.",
    ]


def module_wat(calls, source, note, blit_first):
    """A scene's module from its calls, each at the import table's own type;
    with blit_first, after a frame of x xor y blitted through the cart's own
    palette."""
    with open(os.path.join(ROOT, "wasm-imports.json")) as f:
        table = dict((r["name"], r) for r in json.load(f)["imports"])
    used, strings, body = [], {}, []
    at = [1024]

    def name_of(verb):
        if verb not in table:
            raise ValueError("%s is not in the import table" % verb)
        if verb not in used:
            used.append(verb)
        return "$" + verb

    def expr(a):
        if isinstance(a, tuple):
            if a[0] == "load":
                return "(i32.load (i32.const %d))" % a[1]
            return call(a)
        if isinstance(a, float):
            return "(f32.const %r)" % a
        return "(i32.const %d)" % a

    def call(c):
        parts = []
        for a in c[1:]:
            if isinstance(a, str):
                if a not in strings:
                    strings[a] = at[0]
                    at[0] += (len(a) + 15) & ~15
                parts += ["(i32.const %d)" % strings[a], "(i32.const %d)" % len(a)]
            else:
                parts.append(expr(a))
        return "(call %s %s)" % (name_of(c[0]), " ".join(parts))

    init = []
    target = 0
    for c in calls:
        if c[0] == "make_layer":
            # A trace numbers its layers as the binding hands out handles: from
            # 1, in the order they are made. Made once, in _init.
            if c[1] != len(init) + 1:
                raise ValueError("layer %d made out of order" % c[1])
            init.append("    (drop %s)" % call(("make_layer",) + tuple(c[2:])))
            continue
        if c[0] == "target":
            target = c[1]
        text = call(c)
        body.append("    (drop %s)" % text if table[c[0]]["results"] else "    " + text)
    if target:
        body.append("    " + call(("target", 0)))

    prologue = []
    if blit_first:
        name_of("blit")
        prologue = [
            "    ;; frame[y * 320 + x] = x xor y, blitted with the cart's palette",
            "    (local.set $i (i32.const 0))",
            "    (block $done",
            "      (loop $each",
            "        (br_if $done (i32.ge_u (local.get $i) (i32.const 76800)))",
            "        (i32.store8 offset=65536 (local.get $i)",
            "          (i32.xor (i32.rem_u (local.get $i) (i32.const 320))",
            "                   (i32.div_u (local.get $i) (i32.const 320))))",
            "        (local.set $i (i32.add (local.get $i) (i32.const 1)))",
            "        (br $each)))",
            "    (call $blit (i32.const 65536) (i32.const 0))",
        ]
    imports = []
    for verb in used:
        r = table[verb]
        params = " ".join(r["params"])
        results = " ".join(r["results"])
        imports.append('  (import "moy" "%s" (func $%s%s%s))'
                       % (verb, verb, " (param %s)" % params if params else "",
                          " (result %s)" % results if results else ""))
    datas = ['  (data (i32.const %d) "%s")' % (p, s) for s, p in
             sorted(strings.items(), key=lambda kv: kv[1])]
    pages = 3 if blit_first else 1
    return "\n".join([
        ";; GENERATED by conformance/wasm_run.py --build from %s:" % source,
        ";; edit that, not this file.",
    ] + [";; " + line for line in note] + [
        "(module",
    ] + imports + [
        '  (memory (export "memory") %d %d)' % (pages, pages),
    ] + datas + (['  (func (export "_init")'] + init + ["  )"] if init
                  else ['  (func (export "_init"))']) + [
        '  (func (export "_update") (param f32))',
        '  (func (export "_draw")%s' % (" (local $i i32)" if blit_first else ""),
    ] + prologue + body + [
        "  )",
        ")",
        "",
    ])


# The scenes whose module module_wat() writes: name -> (the calls, where they
# come from, the module's comment, whether a blit comes first).
GENERATED = {
    "verbs": (lambda: VERBS, "wasm_scenes.VERBS", VERBS_NOTE, True),
    "primitives": (primitives_calls, "conformance/traces/primitives.json",
                   PRIMITIVES_NOTE, False),
}
for _name in LAYER_SCENES:
    GENERATED[_name] = ((lambda n=_name: trace_calls(n)),
                        "conformance/traces/%s.json" % _name,
                        layer_note(_name), False)


# name -> the twin that draws its frame. Every scene is also a cart folder
# under conformance/wasm/.
SCENES = [
    ("blit", blit),
    ("blit565", blit565),
    ("read", read),
    ("write", write),
    ("write_again", write_again),
    ("target", target),
    ("snd", snd),
    ("par", par),
    ("verbs", verbs),
    ("primitives", primitives),
] + [(_name, (lambda n=_name: trace_golden(n))) for _name in LAYER_SCENES] + [
    ("trap", trap),
    ("snd_trap", snd_trap),
    ("par_trap", par_trap),
]

# A scene that is another scene's cart run again on the store the other's run
# left, as the cart would run after the player restarted it: write_again is the
# write cart's second run.
AGAIN = {"write_again": "write"}

# A scene whose last tick traps: the host exits non-zero and what it writes is
# the last whole frame, which is the golden.
TRAPS = ("trap", "snd_trap", "par_trap")

# Carts every host must refuse before anything of them runs: exit non-zero,
# no frame. The shape fixtures are libmoy's (libmoy/test/wasm/), the ones
# `moy check` and the WAMR harness refuse too; too_big is well-formed and asks
# for more memory than a player gives.
REFUSED = [
    ("libmoy/test/wasm/foreign_import.moy", "imports from a module that is not \"moy\""),
    ("libmoy/test/wasm/unknown_import.moy", "imports a name the table does not have"),
    ("libmoy/test/wasm/bad_signature.moy", "imports a row at the wrong type"),
    ("libmoy/test/wasm/memory_mismatch.moy", "its memory is not the manifest's"),
    ("libmoy/test/wasm/missing_export.moy", "no _draw"),
    ("libmoy/test/wasm/start_function.moy", "a start function"),
    ("conformance/wasm/too_big.moy", "4 GiB of memory"),
]
