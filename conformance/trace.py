"""Traces: how a scene reaches an implementation that isn't Python.

A scene (scenes.py) is Python, which is fine for moycore and useless for a C
core, a browser player or an ESP32 firmware. So a scene is RECORDED once into a
flat list of cart-level verb calls:

    [["cls", 1], ["rect", 8, 8, 60, 40, 3], ["circ", 120, 30, 20, 8], ...]

That list is the portable artifact. Two things read it:

  * `to_lua` turns it into a real moy cart, which is what SPEC.md 11 actually
    asks for ("the suite is a set of carts"). Any conforming host runs it --
    including the WebAssembly player, which SPEC.md 11 makes the tiebreaker for
    golden frames.
  * `replay` runs it back through a Canvas, which is how the build verifies the
    recording is faithful before shipping it.

A trace replayer is ~40 lines in any language, so an implementer porting moy
can check their raster long before they have a Lua VM wired up. That is the
point: conformance should be reachable early, not only at the end.

Recorded calls are CART-facing (`spr(n, ...)`, not `spr_tile(sheet, n, ...)`)
because the cart-facing verb table is what SPEC.md specifies and what a Lua
cart calls.
"""

import json


class RecordingCanvas:
    """Wraps a Canvas: draws for real, and records what a cart would have
    called to produce the same thing."""

    def __init__(self, canvas, sheet=None, tilemap=None):
        self._c = canvas
        self._sheet = sheet
        self._tilemap = tilemap
        self.calls = []

    # Pass-through verbs whose cart signature matches the canvas one exactly.
    def _rec(self, name, *args):
        self.calls.append([name] + [self._plain(a) for a in args])

    @staticmethod
    def _plain(v):
        if isinstance(v, bool):
            return v
        if isinstance(v, float) and v == int(v):
            return int(v)
        return v

    def cls(self, c=0):
        self._rec("cls", c); return self._c.cls(c)

    def pix(self, x, y, c=None):
        if c is None:
            return self._c.pix(x, y)
        self._rec("pix", x, y, c); return self._c.pix(x, y, c)

    def line(self, x0, y0, x1, y1, c):
        self._rec("line", x0, y0, x1, y1, c); return self._c.line(x0, y0, x1, y1, c)

    def rect(self, x, y, w, h, c):
        self._rec("rect", x, y, w, h, c); return self._c.rect(x, y, w, h, c)

    def rectb(self, x, y, w, h, c):
        self._rec("rectb", x, y, w, h, c); return self._c.rectb(x, y, w, h, c)

    def circ(self, cx, cy, r, c):
        self._rec("circ", cx, cy, r, c); return self._c.circ(cx, cy, r, c)

    def circb(self, cx, cy, r, c):
        self._rec("circb", cx, cy, r, c); return self._c.circb(cx, cy, r, c)

    def tri(self, x1, y1, x2, y2, x3, y3, c):
        self._rec("tri", x1, y1, x2, y2, x3, y3, c)
        return self._c.tri(x1, y1, x2, y2, x3, y3, c)

    def trib(self, x1, y1, x2, y2, x3, y3, c):
        self._rec("trib", x1, y1, x2, y2, x3, y3, c)
        return self._c.trib(x1, y1, x2, y2, x3, y3, c)

    def print(self, s, x, y, c, scale=1):
        self._rec("print", s, x, y, c); return self._c.print(s, x, y, c)

    def camera(self, x=None, y=None):
        if x is None:
            self._rec("camera")
            return self._c.camera()
        self._rec("camera", x, y); return self._c.camera(x, y)

    def clip(self, x=None, y=None, w=None, h=None):
        if x is None:
            self._rec("clip")
            return self._c.clip()
        self._rec("clip", x, y, w, h); return self._c.clip(x, y, w, h)

    def pal(self, c0=None, c1=None):
        if c0 is None:
            self._rec("pal")
            return self._c.pal()
        self._rec("pal", c0, c1); return self._c.pal(c0, c1)

    def palt(self, c=None, on=None):
        if c is None:
            self._rec("palt")
            return self._c.palt()
        self._rec("palt", c, bool(on)); return self._c.palt(c, on)

    # Verbs whose cart signature drops the asset argument.
    def spr_tile(self, sheet, tile, x, y, colorkey=-1, scale=1, flip=0):
        self._rec("spr", tile, x, y, colorkey, scale, flip)
        return self._c.spr_tile(sheet, tile, x, y, colorkey, scale, flip)

    def sspr(self, sheet, sx, sy, sw, sh, dx, dy, dw=None, dh=None,
             colorkey=-1, flip=0):
        dw = sw if dw is None else dw
        dh = sh if dh is None else dh
        self._rec("sspr", sx, sy, sw, sh, dx, dy, dw, dh, colorkey, flip)
        return self._c.sspr(sheet, sx, sy, sw, sh, dx, dy, dw, dh, colorkey, flip)

    def map(self, tilemap, sheet, mx=0, my=0, w=None, h=None,
            sx=0, sy=0, colorkey=-1, scale=1):
        # Resolve the defaults now: a trace must be self-contained, so "the
        # rest of the map" has to become concrete numbers before it ships.
        w = (tilemap.w - mx) if w is None else w
        h = (tilemap.h - my) if h is None else h
        self._rec("map", mx, my, w, h, sx, sy, colorkey, scale)
        return self._c.map(tilemap, sheet, mx, my, w, h, sx, sy, colorkey, scale)


# The verbs a replayer must implement, and how many arguments each takes in a
# trace. Published so a port can assert it handles all of them.
ARITY = {
    "cls": (1,), "pix": (3,), "line": (5,), "rect": (5,), "rectb": (5,),
    "circ": (4,), "circb": (4,), "print": (4,), "camera": (0, 2),
    "clip": (0, 4), "pal": (0, 2), "palt": (0, 2), "spr": (6,),
    "map": (8,), "tri": (7,), "trib": (7,), "sspr": (10,),
}


def replay(calls, canvas, sheet=None, tilemap=None):
    """Run a trace against a Canvas -- the reference replayer, and the model
    for a port's own."""
    for call in calls:
        verb = call[0]
        a = call[1:]
        if verb == "cls":
            canvas.cls(a[0])
        elif verb == "pix":
            canvas.pix(a[0], a[1], a[2])
        elif verb == "line":
            canvas.line(a[0], a[1], a[2], a[3], a[4])
        elif verb == "rect":
            canvas.rect(a[0], a[1], a[2], a[3], a[4])
        elif verb == "rectb":
            canvas.rectb(a[0], a[1], a[2], a[3], a[4])
        elif verb == "circ":
            canvas.circ(a[0], a[1], a[2], a[3])
        elif verb == "circb":
            canvas.circb(a[0], a[1], a[2], a[3])
        elif verb == "tri":
            canvas.tri(a[0], a[1], a[2], a[3], a[4], a[5], a[6])
        elif verb == "trib":
            canvas.trib(a[0], a[1], a[2], a[3], a[4], a[5], a[6])
        elif verb == "print":
            canvas.print(a[0], a[1], a[2], a[3])
        elif verb == "camera":
            canvas.camera(*a)
        elif verb == "clip":
            canvas.clip(*a)
        elif verb == "pal":
            canvas.pal(*a)
        elif verb == "palt":
            canvas.palt(*a)
        elif verb == "spr":
            canvas.spr_tile(sheet, a[0], a[1], a[2], a[3], a[4], a[5])
        elif verb == "sspr":
            canvas.sspr(sheet, a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7],
                        a[8], a[9])
        elif verb == "map":
            canvas.map(tilemap, sheet, a[0], a[1], a[2], a[3], a[4], a[5],
                       a[6], a[7])
        else:
            raise ValueError("unknown trace verb %r" % (verb,))


def _lua_string(s):
    """A Lua string literal with every byte written explicitly.

    NOT json.dumps: JSON escapes a control character as \\u0000, and Lua 5.4
    spells that \\u{0} -- a JSON string is not a Lua string and pretending
    otherwise produces a cart that will not compile. Lua's \\ddd decimal escape
    is unambiguous and covers every byte.

    Only ASCII reaches here (see the note in scenes.text): a Lua string is a
    BYTE string, so a multi-byte character advances `print` once per byte on a
    real host, and moycore -- iterating a Python str -- would advance once per
    codepoint. The two disagree, and SPEC.md 6 says "codepoints" without saying
    which one it means. Until that is settled the suite stays inside one byte
    per character, where every implementation agrees."""
    out = ['"']
    for ch in s:
        o = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif 0x20 <= o < 0x7F:
            out.append(ch)
        elif o < 256:
            out.append("\\%d" % o)
        else:
            raise ValueError(
                "conformance strings must be single-byte; got U+%04X" % o)
    out.append('"')
    return "".join(out)


def _lua_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return _lua_string(v)
    return repr(v)


def to_lua(calls, title, note=""):
    """A trace -> the main.lua of a conformance cart.

    One static frame: _draw replays the calls and nothing moves, so the golden
    is the same on frame 1 and frame 600. A runner captures whichever frame it
    likes."""
    lines = [
        "-- %s -- a moy conformance cart. GENERATED; do not edit." % title,
        "-- Regenerate with: python3 conformance/build.py",
        "--",
        "-- One static frame replaying a recorded verb trace. Compare the frame",
        "-- your host renders against conformance/golden/%s.png -- SPEC.md 11" % title,
        "-- calls conformance pixel-identical, so any difference is a bug in one",
        "-- of the two implementations and the point is to find out which.",
    ]
    if note:
        lines.append("--")
        for ln in note.strip().split("\n"):
            lines.append("-- " + ln)
    lines.append("")
    lines.append("function _draw()")
    for call in calls:
        args = ", ".join(_lua_value(v) for v in call[1:])
        lines.append("  %s(%s)" % (call[0], args))
    lines.append("end")
    lines.append("")
    return "\n".join(lines)
