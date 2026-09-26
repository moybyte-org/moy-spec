"""The compiled-cart scenes (proposals/wasm-runtime.md), and what each must draw.

Every scene is a runtime "wasm" cart under conformance/wasm/<name>.moy, its
module committed as WAT source (tools/wat.py assembles it), and a Python twin
here that renders the frame the proposal's rules say it draws: the blit's
palette and bytes applied by hand, and every ordinary verb drawn by moycore,
the raster the suite's goldens come from. `conformance/wasm_run.py --build`
writes the goldens from these twins and `conformance/wasm_run.py` holds every
host to them.

A wasm golden is an RGB565 frame (the proposal's Determinism section): W x H
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
    """proposals/wasm-runtime.md's read, from the rule: (answer, bytes)."""
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
    form spelled out with the sentinel proposals/wasm-imports.json gives it."""
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
    with open(os.path.join(ROOT, "proposals", "wasm-imports.json")) as f:
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
    ("target", target),
    ("verbs", verbs),
    ("primitives", primitives),
] + [(_name, (lambda n=_name: trace_golden(n))) for _name in LAYER_SCENES] + [
    ("trap", trap),
]

# A scene whose last tick traps: the host exits non-zero and what it writes is
# the last whole frame, which is the golden.
TRAPS = ("trap",)

# Carts every host must refuse before anything of them runs: exit non-zero,
# no frame. The shape fixtures are libmoy's (libmoy/test/wasm/), the ones
# `moy check` and the WAMR harness refuse too; too_big is well-formed and asks
# for more memory than a player gives.
REFUSED = [
    ("libmoy/test/wasm/foreign_import.moy", "imports from a module that is not \"moy\""),
    ("libmoy/test/wasm/bad_signature.moy", "imports a row at the wrong type"),
    ("libmoy/test/wasm/memory_mismatch.moy", "its memory is not the manifest's"),
    ("libmoy/test/wasm/missing_export.moy", "no _draw"),
    ("libmoy/test/wasm/start_function.moy", "a start function"),
    ("conformance/wasm/too_big.moy", "4 GiB of memory"),
]
