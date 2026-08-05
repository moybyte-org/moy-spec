"""The conformance scenes: one frame each, exercising one area of the raster.

A scene is a plain function of (canvas, sheet, tilemap) that calls console
verbs. Deliberately NOT Lua: these test the RASTER -- what SPEC.md 6, 7.1 and
7.2 say each verb lights up -- and that is a property of the drawing code, not
of the language binding. Keeping them language-free means the same scene can be
driven through moycore, through the reference console's Python canvas, or
through a C core's test harness, and the three can be compared directly.

The Lua-level suite is a different thing and lives elsewhere: examples/verbs.moy
walks the same ground through a real cart, which is what a whole HOST has to
pass. This suite is what a RASTER has to pass. An implementation needs both.

Every scene is deterministic by construction -- no rnd(), no time(), no input.
SPEC.md 9 defines rnd()'s range but not its sequence, so a scene calling it
could not have a golden frame at all (see moycore/api.py's _Rng note).

Adding a scene: append to SCENES, regenerate goldens, and look at the PNG. A
golden nobody has looked at is a record of what the code did, not of what the
spec says.
"""


def _fill_sheet(sheet):
    """Paint the shared test sheet. Tiles are chosen to make failures legible
    in a diff rather than to look nice:

      0  blank                 (map cell 00 / colorkey source)
      1  solid colour 8
      2  a 2-colour checker    (shows scaling and nearest-neighbour errors)
      3  ASYMMETRIC L-shape    (the flip tests are meaningless without it)
      4  a border with a hole  (colorkey and palt)
      5  a vertical gradient   (row order, vertical flip)
    """
    # Tile 0 is left blank: it is blank by convention across the whole PICO-8
    # catalogue, which is why SPEC.md 3.3 makes map cell 00 mean empty.
    def put(tile, x, y, c):
        sheet.tset(tile, x, y, c)
    for y in range(8):
        for x in range(8):
            put(1, x, y, 8)
            put(2, x, y, 12 if (x + y) % 2 else 7)
            put(3, x, y, 0)
            put(4, x, y, 0 if (1 <= x <= 6 and 1 <= y <= 6) else 11)
            put(5, x, y, y + 1)
    # Tile 3: an L that is symmetric under no flip at all.
    for y in range(8):
        put(3, 0, y, 14)
    for x in range(8):
        put(3, x, 7, 14)
    put(3, 6, 0, 10)


def _fill_map(tilemap):
    """A small level with holes, so empty cells (SPEC.md 3.3) are exercised."""
    pattern = (
        "1102200000",
        "0110022000",
        "0011002200",
        "3000110022",
        "0300011002",
        "5030001100",
    )
    for y in range(len(pattern)):
        for x in range(len(pattern[y])):
            v = int(pattern[y][x])
            tilemap.mset(x, y, v - 1 if v else -1)


def primitives(c, sheet, tilemap):
    """Every core drawing verb once, at a size where the rasterization shows."""
    c.cls(1)
    c.rect(8, 8, 60, 40, 3)
    c.rectb(8, 8, 60, 40, 11)
    c.circ(120, 30, 20, 8)
    c.circb(120, 30, 20, 10)
    c.line(160, 8, 260, 48, 7)
    c.line(160, 48, 260, 8, 12)
    c.line(280, 8, 280, 48, 14)          # vertical
    c.line(160, 60, 300, 60, 15)         # horizontal
    for i in range(8):
        c.pix(300 + (i % 4), 70 + (i // 4), 7)
    c.rect(8, 70, 1, 1, 7)               # 1x1 rect
    c.circ(30, 80, 0, 8)                 # r = 0 -> a single pixel
    c.circb(60, 80, 1, 8)                # r = 1 -> the smallest ring
    c.rect(100, 70, 0, 10, 8)            # zero width -> nothing
    c.rect(110, 70, 10, 0, 8)            # zero height -> nothing


def edges(c, sheet, tilemap):
    """Everything hanging off the canvas edge. Clipping bugs live here."""
    c.cls(0)
    c.rect(-20, -20, 60, 60, 8)
    c.rect(300, 220, 60, 60, 11)
    c.rect(-30, 100, 20, 20, 12)         # entirely off to the left
    c.circ(0, 0, 30, 10)
    c.circ(320, 240, 30, 14)
    c.circb(160, -10, 40, 7)
    c.line(-50, 120, 370, 130, 15)
    c.line(160, -50, 170, 290, 6)
    c.print("EDGE", -12, 4, 7)
    c.print("EDGE", 300, 232, 7)
    c.pix(-1, -1, 8)
    c.pix(320, 240, 8)


def text(c, sheet, tilemap):
    """The full printable range, plus what happens outside it."""
    c.cls(1)
    row = 0
    line = ""
    for code in range(0x20, 0x80):
        line += chr(code)
        if len(line) == 32:
            c.print(line, 8, 8 + row * 10, 7)
            line = ""
            row += 1
    if line:
        c.print(line, 8, 8 + row * 10, 7)
    c.print("", 8, 72, 7)
    c.print("negative", -20, 84, 12)
    for i in range(8):
        c.print("colour %d" % i, 8, 96 + i * 9, i + 8)


def text_bytes(c, sheet, tilemap):
    """Bytes outside 0x20-0x7F: SPEC.md 6 says they draw nothing and advance 8px
    like any glyph.

    A core scene, and the one that took the longest to become one. SPEC.md 6
    used to say "codepoints", which is not implementable consistently: a Lua
    string IS a byte string, so a host that decoded before drawing advanced the
    cursor 8px where one that did not advanced 16, and every character after it
    landed somewhere else. The reference console was itself split -- its device
    kernel walked bytes, its host font walked codepoints.

    Getting this scene to pass took the whole chain: the spec saying bytes, both
    rasterizers walking them, the Lua bridge handing back a byte string instead
    of raising UnicodeError on anything past ASCII, a wire form that can carry
    those bytes, and a replayer that reads it. Nothing here is exotic -- it is
    just the first cart that ever printed a byte no one had printed before."""
    # BYTES, not a str: SPEC.md 6 says print walks bytes, and a str would be
    # UTF-8-encoded on the way in -- b"\xff" is one cell, "\xff" would be two.
    c.cls(1)
    c.print(b"A\x00B", 8, 8, 10)
    c.print(b"C\x1fD", 8, 20, 10)
    c.print(b"E\x7fF", 8, 32, 10)          # 0x7F is IN range -- it draws
    c.print(b"G\xffH", 8, 44, 10)
    c.print(b"\x00\x00\x00\x00TAIL", 8, 56, 7)   # blanks still advance
    c.print("caf\u00e9", 8, 68, 11)        # a str: UTF-8, so 5 cells not 4


def camera_clip(c, sheet, tilemap):
    """camera and clip together -- the interaction, not each alone.

    SPEC.md 6: clip is SCREEN space, applied after the camera offset. A cart
    that scrolls the world and clips the HUD depends on exactly that, and an
    implementation that clips in world space passes every single-feature test
    and fails this one."""
    c.cls(1)
    c.camera(20, 10)
    c.rect(0, 0, 40, 40, 8)              # lands at screen -20, -10
    c.camera()
    c.rect(0, 60, 40, 40, 3)             # camera reset -> lands at 0, 60

    c.clip(100, 20, 60, 60)
    c.rect(80, 0, 200, 200, 11)          # only the clip rect fills
    c.circ(130, 50, 40, 10)
    c.clip()
    c.rect(0, 120, 20, 20, 7)            # clip reset -> unclipped

    c.camera(-40, -100)
    c.clip(200, 120, 80, 80)             # SCREEN space: not shifted by camera
    c.rect(0, 0, 400, 400, 12)
    c.print("CLIPPED", 170, 40, 7)
    c.clip()
    c.camera()

    c.clip(10, 200, 0, 0)                # zero-size clip -> nothing draws
    c.rect(0, 190, 300, 40, 14)
    c.clip()
    c.clip(-50, -50, 500, 500)           # oversized clip -> clamps to canvas
    c.rect(280, 200, 60, 60, 15)
    c.clip()


def pal_palt(c, sheet, tilemap):
    """Draw-time remap and sprite transparency, including their interaction."""
    c.cls(0)
    c.rect(8, 8, 40, 40, 8)              # reference: real colour 8
    c.pal(8, 11)
    c.rect(56, 8, 40, 40, 8)             # same call, drawn as 11
    c.print("REMAP", 8, 52, 8)           # pal applies to text
    c.circ(120, 28, 20, 8)               # ... and to primitives
    c.spr_tile(sheet, 1, 150, 8)         # ... and to sprite pixels
    c.pal()
    c.rect(180, 8, 40, 40, 8)            # reset -> colour 8 again

    # pal is DRAW-time (SPEC.md 12.1): pixels already on the canvas do not move.
    c.pal(11, 14)
    c.rect(230, 8, 40, 40, 11)
    c.pal()

    # palt: index 0 transparent, so tile 4's hole shows the background.
    c.rect(0, 70, 320, 60, 3)
    c.spr_tile(sheet, 4, 16, 80, -1, 4)          # opaque: hole is colour 0
    c.palt(0, True)
    c.spr_tile(sheet, 4, 80, 80, -1, 4)          # palt: hole shows green
    c.palt()
    c.spr_tile(sheet, 4, 144, 80, 0, 4)          # colorkey 0: same effect
    c.palt(11, True)
    c.spr_tile(sheet, 4, 208, 80, -1, 4)         # palt on the BORDER colour
    c.palt()

    # pal and palt at once: remap the border, key the hole.
    c.pal(11, 12)
    c.palt(0, True)
    c.spr_tile(sheet, 4, 272, 80, -1, 4)
    c.pal()
    c.palt()


def sprites(c, sheet, tilemap):
    """Flips, scales and colorkeys -- every combination that can be wrong."""
    c.cls(1)
    for i in range(4):
        c.spr_tile(sheet, 3, 8 + i * 24, 8, -1, 1, i)          # flip 0..3 at 1x
    for i in range(4):
        c.spr_tile(sheet, 3, 8 + i * 40, 32, -1, 3, i)         # flip 0..3 at 3x
    for s in range(1, 5):
        c.spr_tile(sheet, 2, 180 + (s - 1) * 30, 8, -1, s)     # checker, 1x..4x
    c.spr_tile(sheet, 5, 8, 140, -1, 4)                        # gradient, row order
    c.spr_tile(sheet, 5, 48, 140, -1, 4, 2)                    # ... flipped vertically
    c.spr_tile(sheet, 4, 96, 140, 11, 4)                       # colorkey on the border
    c.spr_tile(sheet, 0, 140, 140, -1, 4)                      # blank tile
    c.spr_tile(sheet, 511, 180, 140, -1, 4)                    # last legal tile
    c.spr_tile(sheet, 512, 220, 140, -1, 4)                    # past the end: nothing
    c.spr_tile(sheet, -1, 260, 140, -1, 4)                     # negative: nothing
    c.spr_tile(sheet, 3, -6, 200, -1, 2)                       # partly off-canvas
    c.spr_tile(sheet, 3, 306, 200, -1, 2)
    c.camera(-100, -8)                                          # sprites honour camera
    c.spr_tile(sheet, 3, 0, 0, -1, 2)
    c.camera()
    c.clip(140, 190, 24, 24)                                    # ... and clip
    c.spr_tile(sheet, 2, 136, 186, -1, 4)
    c.clip()


def tilemap_scene(c, sheet, tilemap):
    """map() regions, offsets, scale and camera."""
    c.cls(1)
    c.map(tilemap, sheet, 0, 0, 10, 6, 0, 0)
    c.map(tilemap, sheet, 2, 1, 4, 3, 100, 8)          # a sub-region
    c.map(tilemap, sheet, 0, 0, 10, 6, 8, 60, -1, 2)   # scale 2
    c.map(tilemap, sheet, 0, 0, 4, 4, 200, 60, 11)     # colorkey
    c.camera(-10, -160)
    c.map(tilemap, sheet, 0, 0, 6, 4, 0, 0)
    c.camera()
    c.clip(200, 160, 60, 60)
    c.map(tilemap, sheet, 0, 0, 10, 6, 190, 150, -1, 2)
    c.clip()
    c.map(tilemap, sheet, -2, -2, 6, 6, 260, 200)      # region starting out of range


def provisional(c, sheet, tilemap):
    """SPEC.md 6.1 verbs. Excluded from conformance until each clears its
    promotion gates -- kept as a scene so the golden already exists."""
    c.cls(1)
    c.tri(20, 20, 100, 40, 60, 100, 8)
    c.trib(20, 20, 100, 40, 60, 100, 7)
    c.tri(120, 20, 200, 20, 160, 90, 11)      # flat top
    c.tri(120, 100, 200, 100, 160, 30, 12)    # flat bottom
    c.tri(220, 20, 300, 20, 260, 20, 14)      # degenerate: one row
    c.sspr(sheet, 0, 8, 8, 8, 20, 130, 40, 40)             # tile 1 stretched
    c.sspr(sheet, 16, 8, 8, 8, 70, 130, 60, 30)            # non-uniform
    c.sspr(sheet, 24, 8, 8, 8, 140, 130, 40, 40, -1, 1)    # flipped
    c.sspr(sheet, 24, 8, 8, 8, 190, 130, 40, 40, -1, 2)
    c.sspr(sheet, 8, 8, 16, 8, 240, 130, 8, 40)            # squashed
    c.sspr(sheet, 0, 8, 8, 8, 20, 190, 0, 40)              # zero dest: nothing


def provisional_tline(c, sheet, tilemap):
    """SPEC.md 6.1 tline: exactly line()'s pixels, texture-stepped across the
    map in 16.16 fixed point. A separate scene from `provisional` so a host
    that has tri/sspr but not tline fails one scene, not both. Excluded for
    the same reason and by the same rule.

    The map fixture is 20 x 15 cells = a 160 x 120 pixel virtual texture, its
    populated 10 x 6 corner surrounded by empty cells -- so most lines here
    cross both."""
    F = 65536                                     # 1.0 in 16.16
    c.cls(1)
    # A Mode-7-shaped fan: one call per scanline, du widening as the line
    # "recedes". All the perspective is BETWEEN calls, none inside one.
    for i in range(40):
        c.tline(tilemap, sheet, 0, 8 + i, 159, 8 + i,
                0, (i * 3 * F) // 2, F // 4 + i * (F // 64), 0)
    # The same texture under Bresenham's diagonal pixel set.
    c.tline(tilemap, sheet, 170, 8, 300, 60, 0, 0, F // 2, F // 3)
    # Wrap: u starts one full texture-width negative and walks through zero;
    # the texture must repeat, not clamp or vanish.
    c.tline(tilemap, sheet, 0, 60, 159, 60, -160 * F, 4 * F, 2 * F, 0)
    # A raycaster's column: vertical walk, v-stepped.
    c.tline(tilemap, sheet, 310, 8, 310, 100, 4 * F, 0, 0, F // 2)
    # colorkey drops the checker's light squares; palt the dark ones. Same
    # texels, opposite holes.
    c.tline(tilemap, sheet, 8, 110, 120, 110, 0, 24 * F, F // 2, 0, 7)
    c.palt(12, 1)
    c.tline(tilemap, sheet, 8, 116, 120, 116, 0, 24 * F, F // 2, 0)
    c.palt()
    # camera moves where the line LANDS, never what it samples: these two
    # draw identical texel runs 8,6 apart on screen.
    c.tline(tilemap, sheet, 150, 110, 262, 110, 0, 40 * F, F // 2, 0)
    c.camera(-8, -6)
    c.tline(tilemap, sheet, 150, 110, 262, 110, 0, 40 * F, F // 2, 0)
    c.camera()
    # clip: the texture cursor advances under the mask too, so the visible
    # stretch stays texel-aligned with its screen x (u == x * 1.0 here).
    c.clip(8, 130, 60, 20)
    c.tline(tilemap, sheet, 0, 140, 200, 140, 0, 0, F, 0)
    c.clip()
    # A single-pixel line, and a line sampling only empty cells: one texel,
    # then nothing at all.
    c.tline(tilemap, sheet, 200, 100, 200, 100, 0, 0, F, F)
    c.tline(tilemap, sheet, 8, 160, 300, 160, 0, 90 * F, F, 0)


SCENES = (
    ("primitives", primitives),
    ("edges", edges),
    ("text", text),
    ("text_bytes", text_bytes),
    ("camera_clip", camera_clip),
    ("pal_palt", pal_palt),
    ("sprites", sprites),
    ("tilemap", tilemap_scene),
    ("provisional", provisional),
    ("provisional_tline", provisional_tline),
)

# Scenes that exercise SPEC.md 6.1 and are therefore NOT part of conformance
# until each verb clears its promotion gates (SPEC.md 11: reported, not
# counted).
EXCLUDED = ("provisional", "provisional_tline")


def core_scenes():
    return tuple((n, f) for n, f in SCENES if n not in EXCLUDED)
