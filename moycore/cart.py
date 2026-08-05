"""The cart (SPEC.md 3).

A cart is a folder: manifest.json and main.lua required, sprites.moygfx,
map.moymap, sounds.json and config.json optional. How the folder TRAVELS -- a
zip, a git clone, a directory on an SD card -- is packaging, and the spec says
nothing about it.

So neither does the loader. `Cart.from_files` takes a plain {name: bytes} map,
which is what a host has whether it read a directory, unpacked an archive or
fetched the whole thing over HTTP. `load_cart` is the convenience wrapper for
hosts that do have a filesystem.

Two failure modes, kept strictly apart, because SPEC.md 3.4 draws the line and
getting it backwards is how a catalogue develops holes:

  * CAPABILITY fields refuse. An unimplemented `runtime` or `extensions` entry
    means this console cannot run this cart, and saying so is the only honest
    outcome -- running it anyway reports a syntax error in the author's code
    for what is actually a host limitation.
  * COSMETIC fields degrade. A malformed `icon` costs the cart its picture and
    nothing else. A cart with a bad icon is still a perfectly good cart.
"""

import json

from . import palette as _palette
from .sheet import SpriteSheet, TileMap, SheetError

FORMAT = "moy-1"
DEFAULT_MAIN = "main.lua"
DEFAULT_FPS = 30
VALID_FPS = (30, 60)
INPUT_KINDS = ("buttons", "touch", "keyboard")
CANVAS_SIZES = ("320x240", "160x120", "128x128")
ICON_MAX_TILES = 4

MANIFEST = "manifest.json"
SPRITES = "sprites.moygfx"
MAP = "map.moymap"
SOUNDS = "sounds.json"
CONFIG = "config.json"


class CartError(Exception):
    """The cart cannot be loaded. The message is meant to be shown to a person."""


class Unsupported(CartError):
    """The cart is well-formed but this host cannot run it -- an unimplemented
    `runtime` (SPEC.md 15) or `extensions` entry (SPEC.md 10). A distinct type
    because a host should say "this console can't run this" rather than "this
    cart is broken"; they are different sentences to a player."""


def _text(blob):
    if isinstance(blob, bytes) or isinstance(blob, bytearray):
        return bytes(blob).decode("utf-8")
    return blob


def _normalize_icon(value, tile_count):
    """A manifest `icon` -> (tile, w, h), or None.

    Accepts a bare tile id (1x1) or [tile, w, h]. Never raises: an icon outside
    1-4 tiles, or naming tiles past the sheet, is IGNORED and the host draws
    whatever it likes. The bound is what makes the field safe to honour -- a
    launcher decodes many icons at once and an unbounded block would let one
    cart name the whole sheet."""
    if value is None:
        return None
    try:
        if isinstance(value, (list, tuple)):
            if len(value) == 1:
                tile, w, h = int(value[0]), 1, 1
            elif len(value) == 3:
                tile, w, h = int(value[0]), int(value[1]), int(value[2])
            else:
                return None
        else:
            tile, w, h = int(value), 1, 1
    except (TypeError, ValueError):
        return None
    if not (1 <= w <= ICON_MAX_TILES and 1 <= h <= ICON_MAX_TILES):
        return None
    if tile < 0 or tile >= tile_count:
        return None
    return (tile, w, h)


class Cart:
    """A loaded cart: its manifest, its script source and its assets.

    Holds no console state -- no canvas, no VM, no audio. A host builds those
    and points them at this."""

    def __init__(self, manifest, source, sheet=None, tilemap=None,
                 sounds=None, config=None, name=None):
        self.manifest = manifest
        self.source = source
        self.sheet = sheet if sheet is not None else SpriteSheet()
        self.tilemap = tilemap if tilemap is not None else TileMap()
        self.sounds = sounds if sounds is not None else {}
        self.config = config if config is not None else {}
        self.name = name

    # -- the manifest fields a host actually reads --------------------------

    @property
    def title(self):
        return self.manifest.get("title") or self.name or "untitled"

    @property
    def author(self):
        return self.manifest.get("author")

    @property
    def main(self):
        return self.manifest.get("main") or DEFAULT_MAIN

    @property
    def fps(self):
        """30 (default) or 60. A host that cannot sustain 60 for this cart falls
        back to 30 rather than running at an unstable rate in between
        (SPEC.md 5) -- that decision is the host's, made per frame, not here."""
        v = self.manifest.get("fps", DEFAULT_FPS)
        return v if v in VALID_FPS else DEFAULT_FPS

    @property
    def runtime(self):
        return self.manifest.get("runtime") or "lua"

    @property
    def extensions(self):
        v = self.manifest.get("extensions")
        return list(v) if isinstance(v, (list, tuple)) else []

    @property
    def input_kinds(self):
        """Which input groups the cart reads, or None when undeclared.

        Advisory only (SPEC.md 7.3): a host uses it to decide whether to draw
        soft controls. None means "show everything". It is never a requirement
        -- a cart listing "touch" still plays on a device without one, because
        every cart MUST be playable with buttons alone."""
        v = self.manifest.get("input")
        if not isinstance(v, (list, tuple)):
            return None
        kinds = [k for k in v if k in INPUT_KINDS]
        return kinds or None

    @property
    def palette(self):
        """The cart's colour table: its own 64 if it shipped one, else the
        default (SPEC.md 2.2)."""
        v = self.manifest.get("palette")
        if v is None:
            return _palette.MOY64
        return _palette.parse(v)

    @property
    def canvas_size(self):
        """The declared raster as (w, h): (320, 240) unless the manifest says
        smaller (SPEC.md 3.1). Hand this to Canvas(width, height)."""
        w, h = (self.manifest.get("canvas") or CANVAS_SIZES[0]).split("x")
        return int(w), int(h)

    def icon(self):
        return _normalize_icon(self.manifest.get("icon"), self.sheet.count)

    # -- construction -------------------------------------------------------

    @classmethod
    def from_files(cls, files, name=None, supported_extensions=(),
                   supported_runtimes=("lua",)):
        """Build from a {filename: bytes-or-str} map.

        `supported_extensions` / `supported_runtimes` are what THIS host
        implements. Both are checked before anything else is parsed, so a cart
        the console cannot run is refused before it costs a sheet decode."""
        if MANIFEST not in files:
            raise CartError("no %s -- a cart folder must have one (SPEC.md 3)" % MANIFEST)
        try:
            manifest = json.loads(_text(files[MANIFEST]))
        except ValueError as exc:
            raise CartError("%s is not valid JSON: %s" % (MANIFEST, exc))
        if not isinstance(manifest, dict):
            raise CartError("%s must be a JSON object" % MANIFEST)

        fmt = manifest.get("format")
        if fmt != FORMAT:
            raise CartError('format is %r, expected "%s"' % (fmt, FORMAT))
        if not manifest.get("title"):
            raise CartError("manifest has no title (required, SPEC.md 3.1)")

        runtime = manifest.get("runtime") or "lua"
        if runtime not in supported_runtimes:
            raise Unsupported(
                'this console has no "%s" runtime; it can run: %s'
                % (runtime, ", ".join(supported_runtimes)))

        exts = manifest.get("extensions") or []
        if isinstance(exts, (list, tuple)):
            missing = [e for e in exts if e not in supported_extensions]
            if missing:
                raise Unsupported(
                    "this console does not implement: %s" % ", ".join(str(m) for m in missing))

        # canvas is the other capability field (SPEC.md 1, 3.1): a size outside
        # the closed set is refused, never run at the wrong dimensions.
        cv = manifest.get("canvas")
        if cv is not None and cv not in CANVAS_SIZES:
            raise Unsupported(
                'this console has no %r canvas; a moy-1 cart declares one of: %s'
                % (cv, ", ".join(CANVAS_SIZES)))

        main = manifest.get("main") or DEFAULT_MAIN
        if main not in files:
            raise CartError("manifest names main %r but the cart has no such file" % main)
        source = _text(files[main])

        sheet = SpriteSheet()
        if SPRITES in files:
            try:
                sheet = SpriteSheet.from_hex(_text(files[SPRITES]))
            except SheetError as exc:
                raise CartError("%s: %s" % (SPRITES, exc))

        tilemap = TileMap()
        if MAP in files:
            try:
                tilemap = TileMap.from_hex(_text(files[MAP]))
            except SheetError as exc:
                raise CartError("%s: %s" % (MAP, exc))

        sounds = {}
        if SOUNDS in files:
            try:
                sounds = json.loads(_text(files[SOUNDS])) or {}
            except ValueError as exc:
                raise CartError("%s is not valid JSON: %s" % (SOUNDS, exc))

        # config.json is the author's own tuning surface, hand-edited by
        # definition (SPEC.md 9). A syntax error in it must not cost the player
        # the game -- cfg() falls back to its defaults and the cart runs.
        config = {}
        if CONFIG in files:
            try:
                config = json.loads(_text(files[CONFIG])) or {}
            except ValueError:
                config = {}

        # A cart-supplied palette is validated at load so a bad one is a load
        # error rather than a crash on the first cls().
        if manifest.get("palette") is not None:
            try:
                _palette.parse(manifest["palette"])
            except Exception as exc:
                raise CartError("manifest palette: %s" % exc)

        return cls(manifest, source, sheet, tilemap, sounds, config, name=name)


def load_cart(path, **kw):
    """Read a .moy folder (or a packed .moy file) from disk.

    Host convenience only -- moycore itself never touches a filesystem, so a
    browser or a frozen firmware image can use `Cart.from_files` instead."""
    import os

    if not os.path.isdir(path):
        from .pack import read_pack
        files = read_pack(path)
        name = os.path.basename(path)
        if name.endswith(".moy"):
            name = name[:-4]
        return Cart.from_files(files, name=name, **kw)

    files = {}
    for entry in os.listdir(path):
        full = os.path.join(path, entry)
        if os.path.isfile(full):
            f = open(full, "rb")
            try:
                files[entry] = f.read()
            finally:
                f.close()
    name = os.path.basename(os.path.normpath(path))
    if name.endswith(".moy"):
        name = name[:-4]
    return Cart.from_files(files, name=name, **kw)
