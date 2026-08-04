"""The raster (SPEC.md 1, 6, 7.1, 7.2).

A Canvas is 320x240 bytes of palette index -- one byte per pixel, origin
top-left, +x right, +y down. Every drawing verb in the spec lands here, and this
file is the normative answer to "what exactly does circ(cx, cy, r, c) light up".
That is the point of it existing in readable form: prose cannot specify a
midpoint circle to the pixel, and a .wasm blob will not tell you.

Draw state is the four things SPEC.md 6 lists -- camera, clip, pal, palt. Every
primitive funnels through `_put` (per-pixel verbs) or `rect` (span verbs), and
those two apply all four, so a verb added later inherits them by construction
rather than by remembering to.

WHAT IS NOT HERE, on purpose: sprite batching, tilemap caching, sub-rect
viewports, partial-frame restore. Those are host performance work -- real and
worth doing, and the reference console does all of them -- but they are
invisible to a cart and they are not what an implementer needs to read. A host
that adds them owes exactly one thing: the same pixels this file produces.

Pixel semantics here are the reference console's, verified byte-for-byte by
conformance/test_parity.py.
"""

from . import font as _font
from . import palette as _palette

WIDTH = 320
HEIGHT = 240

_PAL_IDENTITY = bytes(range(64))
_PALT_OPAQUE = bytes(64)


class Image:
    """A blittable rectangle of palette indices.

    `pix` is any indexable of per-pixel indices; `transparent` is the index to
    skip (-1 = fully opaque). Sheet tiles arrive as these, and so does anything
    a host wants to hand `spr` directly."""

    __slots__ = ("w", "h", "pix", "transparent")

    def __init__(self, width, height, pix, transparent=-1):
        self.w = width
        self.h = height
        self.pix = pix
        self.transparent = transparent


def tri_spans(x1, y1, x2, y2, x3, y3):
    """The horizontal spans of a filled triangle as (x, y, w) triples.

    Integer scanline walk: sort vertices by y, then per row take the long edge
    a->c against whichever short edge is active. Provisional along with tri()
    itself -- SPEC.md 6.1 has not settled."""
    x1 = int(x1); y1 = int(y1)
    x2 = int(x2); y2 = int(y2)
    x3 = int(x3); y3 = int(y3)
    if y1 > y2:
        x1, y1, x2, y2 = x2, y2, x1, y1
    if y1 > y3:
        x1, y1, x3, y3 = x3, y3, x1, y1
    if y2 > y3:
        x2, y2, x3, y3 = x3, y3, x2, y2
    if y3 == y1:                       # flat: one span through all three x
        lo = x1 if x1 < x2 else x2
        if x3 < lo:
            lo = x3
        hi = x1 if x1 > x2 else x2
        if x3 > hi:
            hi = x3
        return [(lo, y1, hi - lo + 1)]
    out = []
    dy_long = y3 - y1
    dy_top = y2 - y1
    dy_bot = y3 - y2
    for y in range(y1, y3 + 1):
        xa = x1 + (x3 - x1) * (y - y1) // dy_long
        if y < y2:                     # dy_top > 0 whenever this branch is taken
            xb = x1 + (x2 - x1) * (y - y1) // dy_top
        elif dy_bot:
            xb = x2 + (x3 - x2) * (y - y2) // dy_bot
        else:
            xb = x3
        if xa > xb:
            xa, xb = xb, xa
        out.append((xa, y, xb - xa + 1))
    return out


class Canvas:
    """The console raster. Default 320x240 (SPEC.md 1); other sizes exist only
    for the `layers` extension (SPEC.md 10)."""

    def __init__(self, width=WIDTH, height=HEIGHT, pal=None):
        self.w = width
        self.h = height
        self.palette = pal if pal is not None else _palette.MOY64
        self.buf = bytearray(width * height)
        self._pal_map = bytearray(_PAL_IDENTITY)
        self._palt = bytearray(_PALT_OPAQUE)
        self.reset_state()

    # -- draw state (SPEC.md 6) ---------------------------------------------

    def reset_state(self):
        """Camera to (0, 0), clip to full screen, pal to identity, palt to all
        opaque.

        A host calls this before each cart frame. Draw state is per-frame and
        must not leak -- not between carts, and not from a host's own UI into a
        cart's first frame. A cart that leaves clip() set on the last line of
        _draw must still get a full canvas on the next one."""
        self._cam_x = 0
        self._cam_y = 0
        self._clip_x0 = 0
        self._clip_y0 = 0
        self._clip_x1 = self.w
        self._clip_y1 = self.h
        self._pal_map[:] = _PAL_IDENTITY
        self._palt[:] = _PALT_OPAQUE

    def camera(self, x=None, y=None):
        """SPEC.md 6: offset subsequent draws by -x, -y. No args resets.
        Returns the previous offset, so a cart can save and restore it."""
        prev = (self._cam_x, self._cam_y)
        if x is None:
            self._cam_x = 0
            self._cam_y = 0
        else:
            self._cam_x = int(x)
            self._cam_y = int(y or 0)
        return prev

    def clip(self, x=None, y=None, w=None, h=None):
        """SPEC.md 6: restrict drawing to a rect. No args resets.

        The rect is SCREEN space -- applied after the camera offset, so a
        scrolling cart's HUD clip stays put while the world moves under it.
        Clamped to the canvas, so an oversized rect is a full screen rather
        than a buffer overrun."""
        if x is None:
            self._clip_x0 = 0
            self._clip_y0 = 0
            self._clip_x1 = self.w
            self._clip_y1 = self.h
            return
        x = int(x)
        y = int(y)
        self._clip_x0 = max(0, x)
        self._clip_y0 = max(0, y)
        self._clip_x1 = min(self.w, x + int(w))
        self._clip_y1 = min(self.h, y + int(h))

    def pal(self, c0=None, c1=None):
        """SPEC.md 6: draw colour c0 as c1. No args resets to identity.

        Draw-TIME only (SPEC.md 12.1): it remaps indices as they are written to
        the canvas, so pixels already on it do not change. Applies to primitives
        and to sprite pixels alike."""
        if c0 is None:
            self._pal_map[:] = _PAL_IDENTITY
            return
        self._pal_map[int(c0) & 63] = int(c1) & 63

    def palt(self, c=None, on=None):
        """SPEC.md 6: mark index c transparent for sprite blits. No args resets
        to all-opaque.

        Consulted IN ADDITION to a call's own colorkey, not instead of it: a
        cart can make index 0 globally transparent and still pass a per-call key
        for one sprite."""
        if c is None:
            self._palt[:] = _PALT_OPAQUE
            return
        self._palt[int(c) & 63] = 1 if on else 0

    # -- primitives (SPEC.md 6) ---------------------------------------------

    def _put(self, x, y, ci):
        """One camera-offset, clipped, pal-remapped pixel. Every per-pixel verb
        goes through here, which is why they all honour all four state pieces."""
        x = x - self._cam_x
        y = y - self._cam_y
        if not (self._clip_x0 <= x < self._clip_x1
                and self._clip_y0 <= y < self._clip_y1):
            return
        self.buf[y * self.w + x] = self._pal_map[ci & 63]

    def cls(self, c=0):
        """Clear to colour c.

        Ignores camera and clip -- it is a full-surface reset, not a rect. It
        does honour pal, so a cart running a global recolour clears to the
        remapped colour rather than punching an unremapped hole in its own
        effect."""
        self.buf[:] = bytes((self._pal_map[int(c) & 63],)) * (self.w * self.h)

    def pix(self, x, y, c=None):
        """Read the index at (x, y) with two args, write it with three.

        Reads are camera-relative too, so a cart that sets a camera and then
        probes a world coordinate gets the pixel it drew there. Out of bounds
        reads 0."""
        x = int(x) - self._cam_x
        y = int(y) - self._cam_y
        if c is None:
            if 0 <= x < self.w and 0 <= y < self.h:
                return self.buf[y * self.w + x]
            return 0
        if not (self._clip_x0 <= x < self._clip_x1
                and self._clip_y0 <= y < self._clip_y1):
            return None
        self.buf[y * self.w + x] = self._pal_map[int(c) & 63]
        return None

    def line(self, x0, y0, x1, y1, c):
        """Bresenham, both endpoints inclusive."""
        x0 = int(x0); y0 = int(y0)
        x1 = int(x1); y1 = int(y1)
        ci = int(c) & 63
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            self._put(x0, y0, ci)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def rect(self, x, y, w, h, c):
        """FILLED rectangle (SPEC.md 6 -- rectb is the outline).

        The span path: camera-offset the corner, intersect with the clip rect,
        write whole rows. Every span-shaped verb (circ, tri, scaled spr) routes
        through here so they clip identically."""
        x = int(x) - self._cam_x
        y = int(y) - self._cam_y
        x0 = max(self._clip_x0, x)
        y0 = max(self._clip_y0, y)
        x1 = min(self._clip_x1, x + int(w))
        y1 = min(self._clip_y1, y + int(h))
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes((self._pal_map[int(c) & 63],)) * (x1 - x0)
        buf = self.buf
        width = self.w
        n = x1 - x0
        for yy in range(y0, y1):
            base = yy * width + x0
            buf[base:base + n] = row

    def rectb(self, x, y, w, h, c):
        """Rectangle OUTLINE: four one-pixel rects, so the corners are written
        twice and the whole thing clips like any other span verb."""
        x = int(x); y = int(y)
        w = int(w); h = int(h)
        self.rect(x, y, w, 1, c)
        self.rect(x, y + h - 1, w, 1, c)
        self.rect(x, y, 1, h, c)
        self.rect(x + w - 1, y, 1, h, c)

    def circ(self, cx, cy, r, c):
        """FILLED circle: one span per row, half-width from the circle equation
        truncated toward zero. r < 0 draws nothing; r == 0 is a single pixel."""
        cx = int(cx); cy = int(cy); r = int(r)
        for dy in range(-r, r + 1):
            span = int((r * r - dy * dy) ** 0.5)
            self.rect(cx - span, cy + dy, 2 * span + 1, 1, c)

    def circb(self, cx, cy, r, c):
        """Circle OUTLINE: midpoint algorithm, eight-way symmetry. Not the
        boundary of circ() -- an outline and a fill are different rasterizations
        and the spec keeps them as separate verbs for exactly that reason."""
        cx = int(cx); cy = int(cy); r = int(r)
        ci = int(c) & 63
        x = r
        y = 0
        err = 0
        while x >= y:
            for px, py in ((x, y), (y, x), (-y, x), (-x, y),
                           (-x, -y), (-y, -x), (y, -x), (x, -y)):
                self._put(cx + px, cy + py, ci)
            y += 1
            if err <= 0:
                err += 2 * y + 1
            else:
                x -= 1
                err -= 2 * x + 1

    def tri(self, x1, y1, x2, y2, x3, y3, c):
        """FILLED triangle. PROVISIONAL -- SPEC.md 6.1, not part of core 0.1."""
        for sx, sy, sw in tri_spans(x1, y1, x2, y2, x3, y3):
            self.rect(sx, sy, sw, 1, c)

    def trib(self, x1, y1, x2, y2, x3, y3, c):
        """Triangle OUTLINE. PROVISIONAL -- SPEC.md 6.1."""
        self.line(x1, y1, x2, y2, c)
        self.line(x2, y2, x3, y3, c)
        self.line(x3, y3, x1, y1, c)

    def print(self, s, x, y, c):
        """Text at a fixed 8px cell (SPEC.md 6 gives print no scale parameter).

        Goes through _put per lit pixel, so text honours camera, clip and pal
        like everything else."""
        ci = int(c) & 63
        put = self._put

        def emit(px, py):
            put(px, py, ci)

        _font.draw(emit, s, x, y)

    # -- sprites and map (SPEC.md 7.1, 7.2) ---------------------------------

    def spr(self, img, x, y, scale=1, flip=0):
        """Blit an Image at (x, y).

        flip: 0 none, 1 horizontal, 2 vertical, 3 both -- the SOURCE read is
        mirrored, so a flipped sprite occupies the same destination rect.
        `scale` is an integer enlargement: each source pixel becomes a
        scale x scale block.

        A pixel is skipped when it matches the image's transparent index, is
        negative, or is marked transparent by palt. Those three are checked
        independently because they come from three different places -- the
        call's colorkey, the image's own key, and the cart's global palt."""
        x = int(x); y = int(y)
        scale = int(scale)
        flip = int(flip)
        fx = flip & 1
        fy = (flip >> 1) & 1
        t = img.transparent
        iw = img.w
        ih = img.h
        pix = img.pix
        palt = self._palt
        if scale <= 1:
            for sy in range(ih):
                ssy = (ih - 1 - sy) if fy else sy
                base = ssy * iw
                ty = y + sy
                for sx in range(iw):
                    ssx = (iw - 1 - sx) if fx else sx
                    p = pix[base + ssx]
                    if p == t or p < 0 or palt[p & 63]:
                        continue
                    self._put(x + sx, ty, p)
            return
        for sy in range(ih):
            ssy = (ih - 1 - sy) if fy else sy
            base = ssy * iw
            for sx in range(iw):
                ssx = (iw - 1 - sx) if fx else sx
                p = pix[base + ssx]
                if p == t or p < 0 or palt[p & 63]:
                    continue
                self.rect(x + sx * scale, y + sy * scale, scale, scale, p)

    def spr_tile(self, sheet, tile, x, y, colorkey=-1, scale=1, flip=0):
        """Blit sheet tile `tile` -- what the cart-facing spr(n, ...) resolves
        to. An out-of-range tile draws nothing rather than raising: SPEC.md 3.2
        says a short sheet leaves the rest blank, so asking for a blank tile is
        legal."""
        img = sheet.tile_image(int(tile), colorkey)
        if img is not None:
            self.spr(img, x, y, scale, flip)

    def sspr(self, sheet, sx, sy, sw, sh, dx, dy, dw=None, dh=None,
             colorkey=-1, flip=0):
        """Stretch a sheet PIXEL region into a dw x dh rect, nearest-neighbour.

        Addresses the sheet in pixels rather than tiles, and its scale is
        arbitrary rather than integer -- that is the whole difference from spr.
        PROVISIONAL: SPEC.md 6.1."""
        sx = int(sx); sy = int(sy); sw = int(sw); sh = int(sh)
        dx = int(dx); dy = int(dy)
        dw = sw if dw is None else int(dw)
        dh = sh if dh is None else int(dh)
        if sw <= 0 or sh <= 0 or dw <= 0 or dh <= 0:
            return
        flip = int(flip)
        fx = flip & 1
        fy = (flip >> 1) & 1
        ck = int(colorkey)
        palt = self._palt
        pget = sheet.pget
        put = self._put
        for j in range(dh):
            v = (j * sh) // dh
            if fy:
                v = sh - 1 - v
            row_y = sy + v
            ty = dy + j
            for i in range(dw):
                u = (i * sw) // dw
                if fx:
                    u = sw - 1 - u
                p = pget(sx + u, row_y)
                if p == ck or palt[p & 63]:
                    continue
                put(dx + i, ty, p)

    def map(self, tilemap, sheet, mx=0, my=0, w=None, h=None,
            sx=0, sy=0, colorkey=-1, scale=1):
        """Blit a w x h CELL region of the tilemap (top-left cell mx, my) to
        screen (sx, sy).

        Straight per-cell blit through spr, so camera, clip, pal and palt all
        apply and a map tile is pixel-identical to the same tile drawn by hand.
        Empty cells (SPEC.md 3.3: byte 00) are skipped, leaving whatever was
        underneath -- which is what makes a tilemap composable with a
        background."""
        mx = int(mx); my = int(my)
        scale = int(scale)
        if scale < 1:
            scale = 1
        if w is None:
            w = tilemap.w - mx
        if h is None:
            h = tilemap.h - my
        w = int(w); h = int(h)
        sx = int(sx); sy = int(sy)
        step = sheet.TILE * scale
        cache = {}
        for cy in range(h):
            ty = my + cy
            py = sy + cy * step
            for cx in range(w):
                tid = tilemap.mget(mx + cx, ty)
                if tid < 0:
                    continue
                img = cache.get(tid)
                if img is None:
                    img = sheet.tile_image(tid, colorkey)
                    cache[tid] = img if img is not None else False
                if not img:
                    continue
                self.spr(img, sx + cx * step, py, scale)

    # -- the `layers` extension (SPEC.md 10) --------------------------------

    def new_layer(self, w, h):
        """An off-screen canvas the cart pre-renders a wide level into once.

        EXTENSION, not core: a cart using this declares `layers` in its
        manifest and a host without it refuses the cart cleanly. Each
        full-screen layer costs another 75 KB (SPEC.md 1.1), which is exactly
        why it is not core."""
        return Canvas(int(w), int(h), self.palette)

    def blit_window_from(self, layer, cam_x=0, cam_y=0):
        """Copy the visible w x h window of `layer` into this canvas.

        Opaque row copy, no transparency -- it is the background, drawn first,
        and overwriting erases last frame's sprites for free. Clamped to the
        source bounds. EXTENSION (SPEC.md 10)."""
        cam_x = max(0, int(cam_x))
        cam_y = max(0, int(cam_y))
        dst = self.buf
        src = layer.buf
        dw = self.w
        dh = self.h
        src_w = layer.w
        if src_w <= 0 or dw <= 0 or dh <= 0:
            return
        if cam_x + dw > src_w:
            dw = src_w - cam_x
        if dw <= 0:
            return
        src_rows = len(src) // src_w
        if cam_y + dh > src_rows:
            dh = src_rows - cam_y
        if dh <= 0:
            return
        for row in range(dh):
            d0 = row * self.w
            s0 = (cam_y + row) * src_w + cam_x
            dst[d0:d0 + dw] = src[s0:s0 + dw]

    # -- readout ------------------------------------------------------------

    def to_rgb888(self, pal=None):
        """Resolve every index through the palette -> packed RGB bytes. What a
        host does at flush time, and what the conformance runner hashes."""
        pal = self.palette if pal is None else pal
        rows = [bytes(rgb) for rgb in pal]
        return b"".join(rows[i] for i in self.buf)

    def to_rgb565(self, pal=None):
        """The same readout as big-endian RGB565, the format most target panels
        actually want."""
        pal = self.palette if pal is None else pal
        tab = _palette.rgb565_table(pal)
        out = bytearray(len(self.buf) * 2)
        for i in range(len(self.buf)):
            v = self.buf[i] * 2
            out[i * 2] = tab[v]
            out[i * 2 + 1] = tab[v + 1]
        return bytes(out)

    def copy_from(self, other):
        """Replace this canvas's pixels with another's (same dimensions)."""
        if other.w != self.w or other.h != self.h:
            raise ValueError("canvas size mismatch")
        self.buf[:] = other.buf
