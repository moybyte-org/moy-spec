"""The sprite sheet and tilemap (SPEC.md 3.2, 3.3, 7.1, 7.2).

Both are stored as human-readable hex text, on purpose: a cart is a folder of
text files so your own editor, git and your own art tools already work. A sheet
diff shows which pixels changed.

sprites.moygfx is PICO-8's __gfx__ format extended DOWNWARD -- 128 characters
per line, up to 256 lines, one hex nibble per pixel. A 128x128 PICO-8 sheet is
character-for-character the top half of a moy sheet with tile ids unchanged,
which is what makes converting a back catalogue nearly free. Growing down rather
than sideways is the reason ids never remap.
"""

TILE = 8
COLS = 16
ROWS = 32
SHEET_W = COLS * TILE          # 128
SHEET_H = ROWS * TILE          # 256
TILE_COUNT = COLS * ROWS       # 512 (SPEC.md 1)

MAP_MAX = 128                  # SPEC.md 3.3: 128x128 cells = the 16 KB budget
MAP_MAX_ID = 254               # a cell stores id+1 in one byte

_HEX = "0123456789abcdef"


class SheetError(Exception):
    """A sheet or map blob is malformed past what degrading can cover."""


class SpriteSheet:
    """512 8x8 tiles of 16-colour pixels, addressed row-major by tile id.

    Sprite pixels are indices 0-15 (SPEC.md 2.3) -- not a memory compromise but
    format compatibility, since one nibble per pixel is exactly what PICO-8
    emits. Which sixteen colours those are is the cart's business (SPEC.md 2.2).
    """

    TILE = TILE

    def __init__(self, cols=COLS, rows=ROWS, pix=None):
        self.cols = cols
        self.rows = rows
        self.w = cols * TILE
        self.h = rows * TILE
        self.pix = pix if pix is not None else bytearray(self.w * self.h)
        self.gen = 0               # bumps on write, so a host cache can invalidate
        self._tile_cache = {}
        self._tile_cache_gen = 0

    @property
    def count(self):
        return self.cols * self.rows

    def pget(self, x, y):
        """The index at sheet pixel (x, y); 0 outside the sheet, so sspr reading
        past the edge samples blank rather than raising."""
        if 0 <= x < self.w and 0 <= y < self.h:
            return self.pix[y * self.w + x]
        return 0

    def pset(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.pix[y * self.w + x] = int(c) & 15
            self.gen += 1

    def tile_origin(self, n):
        """SPEC.md 3.2: tile n has its top-left at ((n % 16) * 8, (n // 16) * 8)."""
        return (n % self.cols) * TILE, (n // self.cols) * TILE

    def tget(self, n, lx, ly):
        ox, oy = self.tile_origin(n)
        return self.pget(ox + lx, oy + ly)

    def tset(self, n, lx, ly, c):
        ox, oy = self.tile_origin(n)
        self.pset(ox + lx, oy + ly, c)

    def tile_image(self, n, transparent=-1):
        """Tile n as a blittable Image, or None when n is out of range.

        Memoised per (n, transparent) and dropped when `gen` bumps. The memo is
        not just speed: a host that dedups sprites by object identity (a browser
        atlas, a device RGB565 bake) needs the same tile to keep coming back as
        the same object across frames."""
        from .canvas import Image
        if n < 0 or n >= self.count:
            return None
        if self._tile_cache_gen != self.gen:
            self._tile_cache = {}
            self._tile_cache_gen = self.gen
        key = (n, transparent)
        img = self._tile_cache.get(key)
        if img is not None:
            return img
        ox, oy = self.tile_origin(n)
        w = self.w
        pix = []
        for ly in range(TILE):
            base = (oy + ly) * w + ox
            for lx in range(TILE):
                pix.append(self.pix[base + lx])
        img = Image(TILE, TILE, pix, transparent)
        self._tile_cache[key] = img
        return img

    def is_blank(self):
        for p in self.pix:
            if p:
                return False
        return True

    # -- sprites.moygfx -----------------------------------------------------

    def to_hex(self):
        """Serialize to sprites.moygfx: one nibble per pixel, `w` chars per
        line. Trailing all-zero lines are dropped -- SPEC.md 3.2 says a short
        sheet leaves the rest blank, so writing 256 lines of zeros for a cart
        using twelve tiles is noise in every diff."""
        w = self.w
        lines = []
        for y in range(self.h):
            base = y * w
            lines.append("".join(_HEX[self.pix[base + x] & 15] for x in range(w)))
        while lines and not lines[-1].strip("0"):
            lines.pop()
        return "\n".join(lines)

    @classmethod
    def from_hex(cls, text, cols=COLS, rows=ROWS):
        """Parse a sprites.moygfx blob.

        Tolerant in exactly the direction SPEC.md 3.2 requires -- a short sheet
        leaves the remaining tiles blank, and hosts MUST accept it -- and strict
        about the rest: a non-hex character or an overlong line is a malformed
        file, not something to guess at."""
        sheet = cls(cols, rows)
        w = sheet.w
        y = 0
        for raw in str(text).split("\n"):
            line = raw.strip()
            if not line:
                continue
            if y >= sheet.h:
                raise SheetError("sheet has more than %d rows" % sheet.h)
            if len(line) > w:
                raise SheetError("sheet row %d is %d chars, max %d" % (y, len(line), w))
            base = y * w
            for x in range(len(line)):
                ch = line[x]
                v = _HEX.find(ch.lower())
                if v < 0:
                    raise SheetError("sheet row %d col %d: %r is not a hex digit"
                                     % (y, x, ch))
                sheet.pix[base + x] = v
            y += 1
        sheet.gen += 1
        return sheet


class TileMap:
    """A grid of tile ids laid over a sheet (SPEC.md 3.3).

    One byte per cell holding `tile_id + 1`, so 00 is empty and an all-zero map
    is genuinely blank. Ids therefore run 0-254 and sheet tile 255 cannot be
    placed -- level geometry rarely needs more than 254 distinct tiles, and
    holding a cell to one byte is what keeps the whole map inside the 16 KB the
    host reserved."""

    EMPTY = -1
    MAX_ID = MAP_MAX_ID

    def __init__(self, w=20, h=15, cells=None):
        self.w = w
        self.h = h
        self.cells = cells if cells is not None else bytearray(w * h)
        self.gen = 0

    def mget(self, x, y):
        """Tile id at a cell; -1 for empty OR out of range (SPEC.md 7.2).

        Those two collapse deliberately: a cart walking off the edge of its
        level should see the same nothing it sees in a hole, so collision code
        needs no bounds check of its own."""
        x = int(x); y = int(y)
        if 0 <= x < self.w and 0 <= y < self.h:
            return self.cells[y * self.w + x] - 1
        return self.EMPTY

    def mset(self, x, y, tile):
        """Write a cell; a negative id clears it. Out-of-range cells are
        dropped, matching mget's read side."""
        x = int(x); y = int(y)
        if not (0 <= x < self.w and 0 <= y < self.h):
            return
        tile = int(tile)
        if tile < 0:
            v = 0
        else:
            if tile > self.MAX_ID:
                tile = self.MAX_ID
            v = tile + 1
        self.cells[y * self.w + x] = v
        self.gen += 1

    def is_blank(self):
        for c in self.cells:
            if c:
                return False
        return True

    # -- map.moymap ---------------------------------------------------------

    def to_hex(self):
        """Header line `w h`, then h rows of w*2 hex digits."""
        out = ["%d %d" % (self.w, self.h)]
        w = self.w
        for y in range(self.h):
            base = y * w
            out.append("".join("%02x" % self.cells[base + x] for x in range(w)))
        return "\n".join(out)

    @classmethod
    def from_hex(cls, text, default_w=20, default_h=15):
        """Parse a map.moymap blob.

        A map declaring dimensions past 128x128 is REFUSED, not clamped
        (SPEC.md 3.3): the host reserved 16 KB for the tilemap and a cart asking
        for more has to be told, rather than quietly getting a level with its
        right half missing."""
        lines = []
        for raw in str(text).split("\n"):
            s = raw.strip()
            if s:
                lines.append(s)
        w, h = default_w, default_h
        body = lines
        if lines:
            head = lines[0].split()
            if len(head) == 2:
                try:
                    w = int(head[0])
                    h = int(head[1])
                    body = lines[1:]
                except ValueError:
                    pass
        if w < 1 or h < 1:
            raise SheetError("map dimensions must be positive, got %dx%d" % (w, h))
        if w > MAP_MAX or h > MAP_MAX:
            raise SheetError(
                "map is %dx%d; SPEC.md 3.3 caps each dimension at %d "
                "(a host must reject this rather than allocate past its budget)"
                % (w, h, MAP_MAX))
        tm = cls(w, h)
        for y in range(min(h, len(body))):
            row = body[y]
            base = y * w
            for x in range(min(w, len(row) // 2)):
                pair = row[x * 2:x * 2 + 2]
                try:
                    tm.cells[base + x] = int(pair, 16)
                except ValueError:
                    raise SheetError("map row %d col %d: %r is not a hex byte"
                                     % (y, x, pair))
        tm.gen += 1
        return tm
