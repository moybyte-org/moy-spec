"""The memory floor (SPEC.md 1.1), as numbers a tool can check.

The console is a fixed-size machine and the spec says exactly how big. A cart
author has no way to find out they overran it except by owning the tightest
hardware -- which is backwards, and is what this module fixes: the budget is
data, so `moy check` can answer "will this fit an ESP32-S3" from a laptop.

What is statically knowable and what is not, kept honest:

  * The sheet, the tilemap and the framebuffer are FIXED sizes. A cart either
    declares dimensions that fit or it does not, and that is decidable.
  * The cart heap is RUNTIME. 192 KB holds the Lua VM and everything the cart
    allocates, and no static analysis of a script tells you what it will
    allocate in level 7. Source size is reported as a signal, never as a
    verdict -- SPEC.md 1.1 calibrates a fully-bridged cart at ~41 KB of Lua
    heap, so 192 KB is generous and source bytes are not the binding
    constraint.
"""

KB = 1024

FRAMEBUFFER = 75 * KB          # 320x240 at one byte per index (76800, rounded)
SPRITE_SHEET = 32 * KB         # 128x256, one byte per pixel in RAM
TILEMAP = 16 * KB              # up to 128x128 cells, one byte each
CART_HEAP = 192 * KB           # the Lua VM and everything the cart allocates
AUDIO = 8 * KB                 # bank plus mix buffer

CORE_TOTAL = 400 * KB          # "with headroom" -- SPEC.md 1.1
LAYER = 75 * KB                # each full-screen off-screen buffer (SPEC.md 10)
LAYERS_TOTAL = 1024 * KB

# What the assets ACTUALLY occupy, as opposed to what the host reserves.
FRAMEBUFFER_EXACT = 320 * 240
SPRITE_SHEET_EXACT = 128 * 256
TILEMAP_EXACT = 128 * 128


def table(layers=False):
    """The §1.1 allocation table as (name, bytes, note) rows."""
    rows = [
        ("Framebuffer", FRAMEBUFFER,
         "320x240 at one byte per index; RGB565 direct costs 150 KB instead"),
        ("Sprite sheet", SPRITE_SHEET, "128x256 pixels, one byte per pixel"),
        ("Tilemap", TILEMAP, "one byte per cell, up to 128x128"),
        ("Cart heap", CART_HEAP, "the Lua VM and everything the cart allocates"),
        ("Audio", AUDIO, "bank plus mix buffer"),
    ]
    if layers:
        rows.append(("layers extension", LAYERS_TOTAL - CORE_TOTAL,
                     "each full-screen off-screen buffer is another 75 KB"))
    return rows


def total(layers=False):
    return LAYERS_TOTAL if layers else CORE_TOTAL


def sheet_bytes(sheet):
    """RAM the sheet occupies -- always the full 32 KB, regardless of how many
    lines the file has. A short sheet is a smaller FILE, not a smaller
    allocation: SPEC.md 3.2 leaves the remaining tiles blank, and a host
    reserved room for all 512 either way."""
    return SPRITE_SHEET_EXACT


def tilemap_bytes(tilemap):
    """RAM the tilemap occupies. Unlike the sheet this DOES scale with the
    declared dimensions -- the map header is authoritative and a 20x15 map is
    300 bytes, not 16 KB. The 16 KB is the ceiling a host must be able to
    honour, not a floor every cart pays."""
    return tilemap.w * tilemap.h


def fits(w, h):
    """Does a map of these dimensions fit the reserved tilemap?"""
    return w * h <= TILEMAP_EXACT and w <= 128 and h <= 128


def human(n):
    if n >= KB:
        v = n / float(KB)
        return "%.1f KB" % v if v < 100 else "%d KB" % round(v)
    return "%d B" % n
