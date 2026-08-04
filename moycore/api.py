"""The verb table (SPEC.md 6, 7, 9) and the input model.

`make_api` returns a plain dict of {name: callable}. That is the whole language
seam: a Lua host installs the dict as globals, a C host wraps each entry, the
conformance raster suite calls them directly. moycore does not embed a VM and
does not want to -- SPEC.md 4 says a cart is Lua 5.4, and which Lua that is
(a C VM, a MicroPython usermod, a browser build) is a host's decision.

Everything a cart can reach is in this dict. There is no ambient global, no
import, no way out -- SPEC.md 0's "out of scope, permanently" list is enforced
by there being nothing here to enforce it against.
"""

from . import canvas as _canvas

BUTTONS = ("left", "right", "up", "down", "a", "b", "run")
REQUIRED_BUTTONS = ("left", "right", "up", "down", "a", "b")
PMEM_SLOTS = 256
PMEM_MIN = -2147483648
PMEM_MAX = 2147483647


class Quit(Exception):
    """Raised by quit(). The host catches it and returns to wherever the cart
    was launched from -- it is a normal ending, not an error (SPEC.md 9)."""


class Input:
    """Button, pointer and keyboard state for one tick.

    THE FRAME CONTRACT, and it only reads correctly one way round: the host
    pushes its physical hardware in (`set_held`, `set_pointer`, `push_key`) and
    THEN calls `tick()`, which computes this frame's press edges against last
    frame's state. Only after that are btn/btnp/touch correct.

        inp.set_held(my_buttons())    # 1. push what the hardware says
        inp.tick()                    # 2. compute the edges
        cart_update(dt)               # 3. now the cart may read

    Pushing after `tick()` loses the edge -- btnp would read a transition
    against state that was never snapshotted -- so the order is part of the
    interface, not a style preference.

    The console defines LOGICAL buttons only -- what maps onto `left` is the
    host's business and no two implementations need agree.

    Player 0 is always this console's own controls. Higher slots stay empty
    until a host registers a transport for them, which is what makes a
    two-player cart portable by construction: it asks players() >= 2 at runtime
    and adapts, rather than being refused at load time by every single-pad
    console."""

    def __init__(self, players=1):
        n = max(1, int(players))
        self._held = [set() for _ in range(n)]
        self._prev = [set() for _ in range(n)]
        self._pressed = [set() for _ in range(n)]     # this frame's 0->1 edges
        self._pointer = None           # (x, y, held) or None
        self._ptr_was_held = False     # last frame's held, for the tap edge
        self._ptr_tapped = False
        self._keys = set()
        self._prev_keys = set()
        self._key_pressed = set()
        self._last_key = 0
        self._textmode = False

    # -- host side ----------------------------------------------------------

    def set_held(self, names, player=0):
        """Replace player `player`'s held set. Names outside BUTTONS are
        dropped: a host with extra hardware buttons keeps them to itself, and a
        cart polling for one reads not-pressed exactly as it would on a console
        that hasn't got it."""
        if 0 <= player < len(self._held):
            self._held[player] = set(n for n in names if n in BUTTONS)

    def set_pointer(self, x, y, held):
        self._pointer = (int(x), int(y), bool(held))

    def clear_pointer(self):
        self._pointer = None

    def push_key(self, code):
        self._keys.add(int(code))
        self._last_key = int(code)

    def release_key(self, code):
        self._keys.discard(int(code))

    def tick(self):
        """Latch this frame's press edges. Call AFTER pushing input, BEFORE the
        cart reads (see the class docstring).

        Every edge is computed once here and then only read, which is what makes
        btnp fire exactly once per physical press with no autorepeat
        (SPEC.md 12.2) no matter how many times the cart calls it in a frame."""
        for p in range(len(self._held)):
            self._pressed[p] = self._held[p] - self._prev[p]
            self._prev[p] = set(self._held[p])
        self._key_pressed = self._keys - self._prev_keys
        self._prev_keys = set(self._keys)
        held = self._pointer is not None and self._pointer[2]
        self._ptr_tapped = held and not self._ptr_was_held
        self._ptr_was_held = held

    def end_frame(self):
        self._last_key = 0

    # -- cart side ----------------------------------------------------------

    def players(self):
        return len(self._held)

    def btn(self, name, player=0):
        player = int(player or 0)
        if not (0 <= player < len(self._held)):
            return False
        return name in self._held[player]

    def btnp(self, name, player=0):
        player = int(player or 0)
        if not (0 <= player < len(self._pressed)):
            return False
        return name in self._pressed[player]

    def touch(self):
        """(x, y, tapped, held), or None when the host has no pointer.

        `tapped` is the press edge so a cart scores at most one hit per tap;
        `held` stays true through a drag, so the same cart can also track one."""
        if self._pointer is None:
            return None
        x, y, held = self._pointer
        return (x, y, self._ptr_tapped, held)

    def key(self, code=None):
        if code is None:
            return self._last_key
        return int(code) in self._keys

    def keyp(self, code=None):
        if code is None:
            return self._last_key
        return int(code) in self._key_pressed

    def textmode(self, on=None):
        if on is None:
            return self._textmode
        self._textmode = bool(on)
        return self._textmode


class _Rng:
    """A small deterministic PRNG (xorshift32) behind rnd().

    NOTE FOR THE SPEC: SPEC.md 9 defines rnd()'s RANGE but not its SEQUENCE, so
    two conforming hosts can disagree on every random number and both be right.
    That is fine for gameplay and fatal for golden frames -- a conformance scene
    cannot call rnd() today. Either the spec pins a generator or the suite
    forbids rnd(); this implementation picks a defined one so the question is at
    least askable. Flagged, not decided."""

    def __init__(self, seed=1):
        self.seed(seed)

    def seed(self, s):
        s = int(s) & 0xFFFFFFFF
        self._s = s if s else 0x9E3779B9

    def next_u32(self):
        s = self._s
        s ^= (s << 13) & 0xFFFFFFFF
        s ^= s >> 17
        s ^= (s << 5) & 0xFFFFFFFF
        self._s = s & 0xFFFFFFFF
        return self._s

    def random(self):
        return self.next_u32() / 4294967296.0


class Pmem:
    """256 persistent slots, each one signed 32-bit integer (SPEC.md 9).

    Exactly what SPEC.md 4.2 makes a Lua integer, which is where every stored
    value comes from and returns to -- a wider slot would accept numbers the
    cart could not read back. `flush` is the host's to implement; writes MAY be
    deferred but MUST land before the cart exits."""

    def __init__(self, values=None, on_write=None):
        self.values = [0] * PMEM_SLOTS
        if values:
            for i in range(min(PMEM_SLOTS, len(values))):
                self.values[i] = int(values[i])
        self.dirty = False
        self._on_write = on_write

    def get(self, i):
        i = int(i)
        if 0 <= i < PMEM_SLOTS:
            return self.values[i]
        return 0

    def set(self, i, v):
        i = int(i)
        if not (0 <= i < PMEM_SLOTS):
            return
        v = int(v)
        if v < PMEM_MIN or v > PMEM_MAX:
            v = ((v - PMEM_MIN) % (PMEM_MAX - PMEM_MIN + 1)) + PMEM_MIN
        self.values[i] = v
        self.dirty = True
        if self._on_write is not None:
            self._on_write(i, v)


def make_api(canvas, cart=None, input=None, audio=None, pmem=None,
             clock=None, rng=None, extensions=()):
    """The cart's entire global namespace.

    `canvas` is where drawing lands, `cart` supplies the sheet/tilemap/config,
    `input` the buttons, `audio` the sound backend (None is legal -- SPEC.md 8.3
    says silence is a valid rendering and a cart MUST NOT depend on audio).
    `clock` returns milliseconds since the cart started. `extensions` names the
    standard extensions this host grants, which is what gates the `layers`
    verbs -- a cart that did not declare it never sees them.
    """
    sheet = cart.sheet if cart is not None else None
    tilemap = cart.tilemap if cart is not None else None
    config = cart.config if cart is not None else {}
    inp = input if input is not None else Input()
    mem = pmem if pmem is not None else Pmem()
    r = rng if rng is not None else _Rng()

    if clock is None:
        import time as _time
        _t0 = _time.time()

        def clock():
            return int((_time.time() - _t0) * 1000)

    # -- drawing (SPEC.md 6) ------------------------------------------------

    def spr(n, x, y, colorkey=-1, scale=1, flip=0):
        # SPEC.md 7.1: n is a sheet tile 0-511. A sprite larger than one tile is
        # drawn as its tiles -- adjacent spr calls -- so there is no w/h here.
        if sheet is None:
            return
        canvas.spr_tile(sheet, n, x, y, colorkey, scale, flip)

    def sspr(sx, sy, sw, sh, dx, dy, dw=None, dh=None, colorkey=-1, flip=0):
        if sheet is None:
            return
        canvas.sspr(sheet, sx, sy, sw, sh, dx, dy, dw, dh, colorkey, flip)

    def map_(mx=0, my=0, w=None, h=None, sx=0, sy=0, colorkey=-1, scale=1):
        if sheet is None or tilemap is None:
            return
        canvas.map(tilemap, sheet, mx, my, w, h, sx, sy, colorkey, scale)

    def mget(x, y):
        return tilemap.mget(x, y) if tilemap is not None else -1

    def mset(x, y, tile):
        if tilemap is not None:
            tilemap.mset(x, y, tile)

    # -- audio (SPEC.md 8) --------------------------------------------------
    # Every one of these is a no-op without a backend. SPEC.md 8.3: a host that
    # cannot synthesize MUST NOT error, and silence is a valid rendering.

    def sfx(n, chan=None):
        if audio is not None:
            audio.sfx(n, chan)

    def music(track, loop=True):
        if audio is not None:
            audio.music(track, loop)

    def music_stop():
        if audio is not None:
            audio.music_stop()

    def sound_stop(chan=None):
        if audio is not None:
            audio.sound_stop(chan)

    # -- state and utility (SPEC.md 9) --------------------------------------

    def cfg(key, default=None):
        return config.get(key, default)

    def pmem_(i, v=None):
        if v is None:
            return mem.get(i)
        mem.set(i, v)
        return None

    def rnd(n=1.0):
        return r.random() * n

    def flr(x):
        return int(x // 1)

    def quit_():
        raise Quit()

    api = {
        # drawing
        "cls": canvas.cls,
        "pix": canvas.pix,
        "line": canvas.line,
        "rect": canvas.rect,
        "rectb": canvas.rectb,
        "circ": canvas.circ,
        "circb": canvas.circb,
        "print": canvas.print,
        "camera": canvas.camera,
        "clip": canvas.clip,
        "pal": canvas.pal,
        "palt": canvas.palt,
        # sprites and map
        "spr": spr,
        "map": map_,
        "mget": mget,
        "mset": mset,
        # input
        "btn": inp.btn,
        "btnp": inp.btnp,
        "players": inp.players,
        "touch": inp.touch,
        "key": inp.key,
        "keyp": inp.keyp,
        "textmode": inp.textmode,
        # audio
        "sfx": sfx,
        "music": music,
        "music_stop": music_stop,
        "sound_stop": sound_stop,
        # state and utility
        "time": clock,
        "pmem": pmem_,
        "cfg": cfg,
        "rnd": rnd,
        "flr": flr,
        "quit": quit_,
        "W": canvas.w,
        "H": canvas.h,
        # PROVISIONAL (SPEC.md 6.1) -- present so the suite can exercise them,
        # and excluded from conformance until 6.1 leaves TBD.
        "tri": canvas.tri,
        "trib": canvas.trib,
        "sspr": sspr,
    }

    if "layers" in extensions:
        # SPEC.md 10: granted only to a cart that declared it. A host that hands
        # these out unconditionally breeds carts that run nowhere else, which is
        # the one thing the extension mechanism exists to prevent.
        def make_layer(w, h):
            return canvas.new_layer(w, h)

        def draw_layer(layer, cx=0, cy=0):
            canvas.blit_window_from(layer, cx, cy)

        api["make_layer"] = make_layer
        api["draw_layer"] = draw_layer

    return api


def api_names(extensions=()):
    """The names a conforming host injects -- what SPEC.md 4.1's sandbox ceiling
    is measured against."""
    c = _canvas.Canvas()
    return sorted(make_api(c, extensions=extensions).keys())
