#!/usr/bin/env python3
"""moy -- the cart developer CLI: scaffold, live-run, publish.

A moy cart is a folder of text files, so your own editor, git and your own
art tools already work; this CLI supplies the loop around them.

    moy.py new <name>            scaffold a Lua cart (manifest + main.lua +
                                 moy-api.lua editor stubs -- the Lua language
                                 server reads those for autocomplete + docs)
    moy.py run <cart.moy>        play the cart in your browser with HOT
                                 RELOAD: save a file, the game restarts in
                                 under a second
    moy.py export <cart.moy>     the publishable web bundle: ~1.1MB of static
                                 files that boot straight into the game --
                                 host anywhere (itch.io HTML5 uploads work)
    moy.py port <cart.p8|url>    convert a PICO-8 cart: assets via p8_import,
                 [--zoom [T,B]]  --zoom trims edge rows so the port draws 2x
                                 code mechanically ported to Lua 5.4 under the
                                 p8 compat shim (p8_lua_port)
    moy.py demo                  fetch Celeste Classic (PICO-8), port it, run
                                 it -- the one-command show-off

Before you ship, and to work with the art tools you already own:

    moy.py check <cart.moy>      what the TIGHTEST conforming host would say:
                                 manifest, sandbox ceiling, undeclared
                                 extensions, the SPEC.md 1.1 budget. Findable
                                 from a laptop instead of from a handheld you
                                 do not own
    moy.py pack <cart.moy>       the folder -> ONE file you can attach, link or
                                 list. Deterministic: same folder, same bytes
    moy.py unpack <cart.moyc>    ... and back to a folder
    moy.py gfx <cart.moy>        sprites.moygfx <-> PNG, so Aseprite/GIMP/
          [--import file.png]    Piskel edit your sheet
    moy.py map <cart.moy>        map.moymap <-> CSV, so Tiled edits your level
          [--import file.csv]
    moy.py conform [--player C]  run the conformance suite (SPEC.md 11)
    moy.py player                which player build runner/ holds, and whether
          [--update]             its files still match; --update pins the
          [--channel beta]       latest CONFORMANCE-GATED release, or a local
          [--from dist-spec/]    build if you are working on the player

Pure Python stdlib, no dependencies. The player it wraps is runner/ (see
runner/BUILD.md); the spec it implements is SPEC.md; the console as a library
is moycore/.
"""

import http.server
import json
import os
import shutil
import sys
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
RUNNER = os.path.join(HERE, "runner")
# Which files the player bundle contains is the PLAYER's business, not this
# CLI's -- it grew a worker.js when the console moved off the main thread. So
# the pin (runner/VERSION) is authoritative, and an unpinned runner/ is read
# from disk rather than guessed at. These are the files in runner/ that belong
# to THIS repository rather than to the player, and are never exported.
VERSION_FILE = "VERSION"
RUNNER_NOT_PLAYER = frozenset((VERSION_FILE, "BUILD.md", "THIRD_PARTY.md"))

# Where `moy.py player --update` fetches from. The reference implementation
# publishes a rolling release per branch, and each one is CONFORMANCE-GATED:
# its CI runs this repository's suite against the bundle and refuses to publish
# a player that fails. So "update" cannot quietly hand you a broken tiebreaker.
PLAYER_REPO = "moybyte-org/moybyte"
PLAYER_CHANNELS = {"stable": "player-latest", "beta": "player-beta"}
PLAYER_ASSET = "moy-player.tar.gz"
PLAYER_MANIFEST = "MANIFEST.json"
DEFAULT_PORT = 8323

# The spec manifest (SPEC.md 3.1) -- brand-neutral, fields the spec defines.
# fps 60 is an explicit opt-in (SPEC.md 5): a fresh scaffold trivially sustains
# it, and hosts that can't fall back to the guaranteed 30.
MANIFEST = {
    "format": "moy-1",
    "title": None,                    # filled from the name
    "version": 1,
    "main": "main.lua",
    "fps": 60,
    "input": ["buttons"],
}

MAIN_LUA = """\
-- {title}: a moy cart. Three verbs, called by the console:
--   _init()      once at start
--   _update(dt)  every tick (dt in seconds)
--   _draw()      every frame
-- The full API is documented in moy-api.lua (your editor's Lua language
-- server reads it for autocomplete + hover docs) and in the spec.

local x, y = 160, 120
local speed = 120

function _init()
end

function _update(dt)
  if btn("left") then x = x - speed * dt end
  if btn("right") then x = x + speed * dt end
  if btn("up") then y = y - speed * dt end
  if btn("down") then y = y + speed * dt end
  if x < 8 then x = 8 elseif x > 312 then x = 312 end
  if y < 8 then y = 8 elseif y > 232 then y = 232 end
end

function _draw()
  cls(1)
  circ(x, y, 8, 8)
  circb(x, y, 8, 7)
  print("{title}", 8, 8, 7)
  print("arrows move", 8, 228, 6)
end
"""


def die(msg):
    print("moy: " + msg, file=sys.stderr)
    sys.exit(1)


def cart_dir(arg):
    d = arg if arg.endswith(".moy") else arg + ".moy"
    return os.path.abspath(d)


# --- new ---------------------------------------------------------------------

def cmd_new(args):
    if not args:
        die("usage: moy.py new <name>")
    dst = cart_dir(args[0])
    if os.path.exists(dst):
        die("already exists: " + dst)
    name = os.path.basename(dst)[:-4]
    title = name.replace("_", " ").replace("-", " ").title()
    os.makedirs(dst)
    man = dict(MANIFEST)
    man["title"] = title
    with open(os.path.join(dst, "manifest.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(man, f, indent=2)
        f.write("\n")
    with open(os.path.join(dst, "main.lua"), "w", encoding="utf-8", newline="\n") as f:
        f.write(MAIN_LUA.replace("{title}", title))
    with open(os.path.join(dst, "config.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write("{}\n")
    stubs = os.path.join(HERE, "moy-api.lua")
    if os.path.isfile(stubs):
        shutil.copy(stubs, os.path.join(dst, "moy-api.lua"))
    print("created %s" % dst)
    print("  next: %s run %s" % (sys.argv[0], os.path.relpath(dst)))


# --- run (the hot-reload dev loop) -------------------------------------------

def pack_cart(src):
    """The cart folder as the player's carts.json shape {<name>/<rel>: text}."""
    name = os.path.basename(src.rstrip("/"))
    bundle = {}
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames
                       if d not in ("thumbs", "__pycache__", ".git")]
        for fn in sorted(filenames):
            if fn == "moy-api.lua":     # editor stubs -- never part of the game
                continue
            p = os.path.join(dirpath, fn)
            rel = name + "/" + os.path.relpath(p, src).replace(os.sep, "/")
            try:
                with open(p, encoding="utf-8") as f:
                    bundle[rel] = f.read()
            except (UnicodeDecodeError, OSError):
                pass
    return bundle


def cart_stamp(src):
    """Latest mtime under the cart folder -- the page's reload-poll target."""
    latest = 0.0
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames
                       if d not in ("thumbs", "__pycache__", ".git")]
        for fn in filenames:
            try:
                m = os.stat(os.path.join(dirpath, fn)).st_mtime
            except OSError:
                continue
            if m > latest:
                latest = m
    return "%f" % latest


def cmd_run(args):
    if not args:
        die("usage: moy.py run <cart.moy> [port]")
    src = cart_dir(args[0])
    if not os.path.isdir(src):
        die("no such cart: " + src)
    port = int(args[1]) if len(args) > 1 else DEFAULT_PORT

    class Handler(http.server.SimpleHTTPRequestHandler):
        extensions_map = dict(http.server.SimpleHTTPRequestHandler.extensions_map,
                              **{".mjs": "text/javascript", ".js": "text/javascript",
                                 ".wasm": "application/wasm"})

        def __init__(self, *a, **kw):
            super().__init__(*a, directory=RUNNER, **kw)

        def log_message(self, *a):
            pass

        def end_headers(self):
            # A DEV server must never let the browser cache the player -- a
            # half-cached page (old wasm, new index) is undebuggable.
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def _send(self, body, ctype):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/carts.json":       # packed LIVE from the cart folder
                self._send(json.dumps(pack_cart(src)).encode(), "application/json")
            elif path == "/stamp":          # the reload poll
                self._send(cart_stamp(src).encode(), "text/plain")
            else:
                super().do_GET()

    url = "http://127.0.0.1:%d/?dev=1" % port
    print("moy run: %s" % src)
    print("  %s   (save a file -> the game restarts)" % url)
    with http.server.ThreadingHTTPServer(("0.0.0.0", port), Handler) as srv:
        webbrowser.open(url)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")


# --- export ------------------------------------------------------------------

def cmd_export(args):
    if not args:
        die("usage: moy.py export <cart.moy> [outdir]")
    src = cart_dir(args[0])
    if not os.path.isdir(src):
        die("no such cart: " + src)
    out = os.path.abspath(args[1]) if len(args) > 1 else src[:-4] + "-web"
    os.makedirs(out, exist_ok=True)
    for fn in runner_files():
        shutil.copy(os.path.join(RUNNER, fn), os.path.join(out, fn))
    with open(os.path.join(out, "carts.json"), "w", encoding="utf-8") as f:
        json.dump(pack_cart(src), f)
    print("exported -> %s" % out)
    print("  static files: host anywhere, or zip the folder for itch.io (HTML5)")


# --- port / demo (PICO-8) ----------------------------------------------------

CELESTE_URL = "https://www.lexaloffle.com/bbs/cposts/1/15133.p8.png"
CELESTE_NOTE = """\
  Celeste Classic (PICO-8, 2016) by Maddy Thorson & Noel Berry
  https://www.lexaloffle.com/bbs/?tid=2145 / https://celesteclassic.github.io/
  PICO-8 BBS carts default to CC BY-NC-SA 4.0: the port is for personal /
  development use with attribution -- do not ship it in anything commercial."""


def cmd_port(args):
    import p8_lua_port
    crop = p8_lua_port.parse_zoom(args)
    args = [a for a in args if not a.startswith("--")]
    if crop != (0, 0):        # drop the "T,B" that followed --zoom
        args = [a for a in args if not ("," in a and a.replace(",", "").isdigit())]
    if not args:
        die("usage: moy.py port <cart.p8 | url> [out.moy] [--zoom [T,B]]")
    src = args[0]
    if src.startswith(("http://", "https://")):
        import urllib.request
        local = os.path.abspath(os.path.basename(src.split("?")[0]) or "cart.p8")
        print("fetching %s" % src)
        req = urllib.request.Request(src, headers={"User-Agent": "moy-cli"})
        with urllib.request.urlopen(req) as r, open(local, "wb") as f:
            f.write(r.read())
        src = local
    src = os.path.abspath(src)
    if not os.path.isfile(src):
        die("no such .p8: " + src)
    out = cart_dir(args[1] if len(args) > 1
                   else os.path.splitext(os.path.basename(src))[0])
    p8_lua_port.port(src, out, crop=crop)
    print("ported -> %s" % out)
    print("  PICO-8 carts carry their own licenses (BBS default CC BY-NC-SA")
    print("  4.0) -- ported carts are dev/personal material unless stated.")
    print("  next: %s run %s" % (sys.argv[0], os.path.relpath(out)))


def cmd_demo(args):
    """Fetch + port + run Celeste Classic -- the one-command demo."""
    print(CELESTE_NOTE)
    out = cart_dir("celeste")
    # --zoom belongs to the PORT, not the run, so split it out -- and re-port
    # when it is asked for, or the flag would silently do nothing on the second
    # `demo` (the cart is already on disk, ported at the other scale).
    zoom = []
    if "--zoom" in args:
        i = args.index("--zoom")
        zoom = [args[i]]
        if i + 1 < len(args) and "," in args[i + 1]:
            zoom.append(args[i + 1])
    rest = [a for a in args if a not in zoom]
    if zoom or not os.path.isdir(out):
        cmd_port([CELESTE_URL, "celeste"] + zoom)
    else:
        print("using existing %s" % out)
    cmd_run(["celeste.moy"] + rest)


# --- check / pack / assets / conform -----------------------------------------
#
# These four lean on moycore/ -- the console as a library. They are here rather
# than as separate scripts because they belong to the same loop as `run`: you
# scaffold, you run, you check before you ship. A tool you have to remember the
# name of is a tool nobody runs.

def _moycore():
    sys.path.insert(0, HERE)
    import moycore
    return moycore


def cmd_check(args):
    """Everything decidable about a cart from its own bytes."""
    if not args:
        die("usage: moy.py check <cart.moy>")
    moycore = _moycore()
    from moycore import check as _check
    from moycore import pack as _pack

    src = args[0]
    if os.path.isdir(cart_dir(src)):
        src = cart_dir(src)
        files = _pack.read_folder(src)
    elif os.path.isfile(src):
        files = _pack.read_pack(src)
    else:
        die("no such cart: " + src)

    try:
        cart = moycore.Cart.from_files(files, supported_extensions=("layers", "viewport"))
    except moycore.CartError as exc:
        print("%s: FAILS TO LOAD" % src)
        print("  error  %s" % exc)
        sys.exit(1)

    findings = _check.check_cart(cart, files)
    print("%s -- %s" % (src, cart.title))
    print("  id     %s" % _pack.content_id(files))
    for level, code, msg in findings:
        print("  %-6s %s: %s" % (level, code, msg))
    verdict = _check.worst(findings)
    if verdict == "error":
        print("\nNOT conforming. A strict host may refuse this cart.")
        sys.exit(1)
    if verdict == "warn":
        print("\nRuns, but not everywhere -- see the warnings above.")
        sys.exit(0)
    print("\nOK.")


def cmd_pack(args):
    """Folder -> one deterministic file (see proposals/single-file-cart.md)."""
    if not args:
        die("usage: moy.py pack <cart.moy> [out%s]" % _moycore().pack.EXT)
    moycore = _moycore()
    from moycore import pack as _pack
    src = cart_dir(args[0])
    if not os.path.isdir(src):
        die("no such cart folder: " + src)
    files = _pack.read_folder(src)
    files.pop("moy-api.lua", None)      # editor stubs are never part of the game
    try:
        moycore.Cart.from_files(files, supported_extensions=("layers", "viewport"))
    except moycore.CartError as exc:
        die("refusing to pack a cart that does not load: %s" % exc)
    blob = _pack.pack_bytes(files)
    out = args[1] if len(args) > 1 else src[:-4] + _pack.EXT
    with open(out, "wb") as f:
        f.write(blob)
    print("%s  (%d files, %d bytes)" % (out, len(files), len(blob)))
    print("id %s" % _pack.content_id(files))


def cmd_unpack(args):
    if not args:
        die("usage: moy.py unpack <cart%s> [out.moy]" % _moycore().pack.EXT)
    _moycore()
    from moycore import pack as _pack
    src = args[0]
    if not os.path.isfile(src):
        die("no such file: " + src)
    files = _pack.read_pack(src)
    base = os.path.basename(src)
    if base.endswith(_pack.EXT):
        base = base[:-len(_pack.EXT)]
    out = args[1] if len(args) > 1 else base + ".moy"
    if os.path.exists(out):
        die("already exists: " + out)
    _pack.write_folder(out, files)
    print("%s  (%d files)" % (out, len(files)))


def _sheet_png_palette(cart):
    """The 16 colours a sheet PNG carries. SPEC.md 2.3: sprite pixels are
    indices 0-15, so the export is a 16-colour image -- which is also what makes
    it open correctly as indexed art in Aseprite instead of as RGB the artist
    then has to quantize back."""
    return list(cart.palette[:16])


def cmd_gfx(args):
    """sprites.moygfx <-> PNG."""
    if not args:
        die("usage: moy.py gfx <cart.moy> [--import sheet.png] [--out sheet.png]")
    moycore = _moycore()
    from moycore import png as _png
    src = cart_dir(args[0])
    if not os.path.isdir(src):
        die("no such cart: " + src)
    cart = moycore.load_cart(src)
    gfx_path = os.path.join(src, "sprites.moygfx")

    if "--import" in args:
        png_path = args[args.index("--import") + 1]
        w, h, px = _png.read_rgb(png_path)
        if w != moycore.sheet.SHEET_W:
            die("sheet PNG must be %d pixels wide (this one is %d)"
                % (moycore.sheet.SHEET_W, w))
        if h > moycore.sheet.SHEET_H:
            die("sheet PNG is %d rows; the sheet is at most %d (SPEC.md 3.2)"
                % (h, moycore.sheet.SHEET_H))
        pal16 = _sheet_png_palette(cart)
        sheet = moycore.SpriteSheet()
        inexact = 0
        cache = {}
        for i in range(w * h):
            rgb = px[i]
            v = cache.get(rgb)
            if v is None:
                v = _png.nearest_index(rgb, pal16)
                if tuple(pal16[v]) != rgb:
                    inexact += 1
                cache[rgb] = v
            sheet.pix[i] = v
        with open(gfx_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(sheet.to_hex() + "\n")
        print("wrote %s (%d rows)" % (gfx_path, h))
        if inexact:
            print("  note: %d distinct colours were not in the cart's first 16 and "
                  "were snapped to the nearest; SPEC.md 2.3 holds sprite pixels to "
                  "indices 0-15" % inexact)
        return

    out = args[args.index("--out") + 1] if "--out" in args else src[:-4] + "-sheet.png"
    sheet = cart.sheet
    rows = sheet.h
    while rows > 8 and not any(sheet.pix[(rows - 8) * sheet.w:rows * sheet.w]):
        rows -= 8            # trim trailing blank tile rows, like to_hex does
    _png.write_indexed(out, sheet.w, rows, sheet.pix[:sheet.w * rows],
                       _sheet_png_palette(cart))
    print("%s  (%dx%d, %d tiles)" % (out, sheet.w, rows, (rows // 8) * sheet.cols))


def cmd_map(args):
    """map.moymap <-> CSV."""
    if not args:
        die("usage: moy.py map <cart.moy> [--import level.csv] [--out level.csv] [--tiled]")
    moycore = _moycore()
    src = cart_dir(args[0])
    if not os.path.isdir(src):
        die("no such cart: " + src)
    cart = moycore.load_cart(src)
    map_path = os.path.join(src, "map.moymap")
    # Tiled's CSV export is 1-based with 0 for empty -- which is byte-for-byte
    # what a .moymap cell already stores (SPEC.md 3.3: each cell holds tile_id+1).
    # So --tiled is not a conversion, it is the absence of one.
    tiled = "--tiled" in args

    if "--import" in args:
        csv_path = args[args.index("--import") + 1]
        with open(csv_path, encoding="utf-8") as f:
            text = f.read()
        rows = []
        for line in text.split("\n"):
            line = line.strip().rstrip(",")
            if not line:
                continue
            rows.append([int(v.strip()) for v in line.split(",") if v.strip() != ""])
        if not rows:
            die("%s has no rows" % csv_path)
        h = len(rows)
        w = max(len(r) for r in rows)
        if w > moycore.sheet.MAP_MAX or h > moycore.sheet.MAP_MAX:
            die("map is %dx%d; SPEC.md 3.3 caps each dimension at %d"
                % (w, h, moycore.sheet.MAP_MAX))
        tm = moycore.TileMap(w, h)
        for y in range(h):
            for x in range(len(rows[y])):
                v = rows[y][x]
                tm.mset(x, y, (v - 1) if tiled else v)
        with open(map_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(tm.to_hex() + "\n")
        print("wrote %s (%dx%d)" % (map_path, w, h))
        return

    out = args[args.index("--out") + 1] if "--out" in args else src[:-4] + "-map.csv"
    tm = cart.tilemap
    lines = []
    for y in range(tm.h):
        vals = []
        for x in range(tm.w):
            t = tm.mget(x, y)
            vals.append(str(t + 1 if tiled else t))
        lines.append(",".join(vals))
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print("%s  (%dx%d, %s)" % (out, tm.w, tm.h,
                               "Tiled gids" if tiled else "tile ids, -1 empty"))


def _pin():
    """The pinned player (runner/VERSION), or None if this checkout has none."""
    path = os.path.join(RUNNER, VERSION_FILE)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except ValueError:
        return None


def runner_files():
    """The bundle's files: the pin's list when pinned, else whatever is actually
    in runner/.

    Never a hardcoded list of names that may not exist. A constant saying
    `worker.js` while runner/ predated the worker is exactly how `export` came
    to die on a FileNotFoundError -- the site build caught it, one commit after
    the tooling that introduced it. A pinned file that is missing IS an error
    and says so; an unpinned bundle is simply reported as found."""
    pin = _pin()
    if pin and pin.get("files"):
        want = sorted(pin["files"])
        missing = [n for n in want if not os.path.isfile(os.path.join(RUNNER, n))]
        if missing:
            die("runner/ is missing %s -- the pin (runner/%s) lists it. "
                "Re-run `moy.py player --update`."
                % (", ".join(missing), VERSION_FILE))
        return tuple(want)
    # Unpinned: the player is whatever is there, minus this repository's own
    # documentation of it.
    if not os.path.isdir(RUNNER):
        die("no runner/ -- run `moy.py player --update` to fetch the player")
    found = tuple(sorted(
        f for f in os.listdir(RUNNER)
        if os.path.isfile(os.path.join(RUNNER, f)) and f not in RUNNER_NOT_PLAYER))
    if not found:
        die("runner/ has no player files -- run `moy.py player --update`")
    return found


def _sha256(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _verify(pin, root, label="runner/"):
    """Check every pinned file against its hash. Returns a list of problems."""
    bad = []
    for name in sorted(pin.get("files", {})):
        want = pin["files"][name]["sha256"]
        path = os.path.join(root, name)
        if not os.path.isfile(path):
            bad.append("%s%s is missing" % (label, name))
        elif _sha256(path) != want:
            bad.append("%s%s does not match the pin" % (label, name))
    return bad


def cmd_player(args):
    """Show or update the pinned web player.

    The player is a BUILD, not source -- emsdk plus a MicroPython checkout,
    which is not something this repository asks anyone to reproduce. So it is
    vendored, and this pins WHICH build so the answer to "which player is this"
    is in the tree rather than in someone's memory. `--update` is then an
    ordinary reviewable commit: the pin moves, the hashes move with it.

    Vendored rather than fetched on demand, deliberately: the README promises
    Python and a browser and nothing else, and a `moy.py run` that needs the
    network on first use would not be that.
    """
    channel = "stable"
    if "--channel" in args:
        channel = args[args.index("--channel") + 1]
    if channel not in PLAYER_CHANNELS:
        die("unknown channel %r (want: %s)" % (channel, ", ".join(sorted(PLAYER_CHANNELS))))

    if "--update" not in args:
        pin = _pin()
        if pin is None:
            print("runner/: not pinned (no %s)" % VERSION_FILE)
            print("  this bundle was copied by hand; `moy.py player --update` pins it")
            return
        src = pin.get("source", {})
        print("runner/: %s @ %s" % (pin.get("bundle", "?"), (src.get("commit") or "?")[:12]))
        print("  channel  %s" % pin.get("channel", "?"))
        print("  branch   %s%s" % (src.get("branch", "?"),
                                   "  (BUILT FROM A DIRTY TREE)" if src.get("dirty") else ""))
        bad = _verify(pin, RUNNER)
        for b in bad:
            print("  MISMATCH %s" % b)
        print("  %d files, %s" % (len(pin.get("files", {})),
                                  "all match the pin" if not bad else "SEE ABOVE"))
        if bad:
            sys.exit(1)
        return

    import tarfile
    import tempfile
    import urllib.request

    # --from <dir>: pin a bundle built locally (firmware/web_runner/dist-spec)
    # instead of a release. For anyone working ON the player -- otherwise
    # testing a change to it means pushing, waiting for CI, and pulling back
    # the thing you already have on disk.
    local = args[args.index("--from") + 1] if "--from" in args else None
    tmp = tempfile.mkdtemp(prefix="moy-player-")
    try:
        if local:
            if not os.path.isfile(os.path.join(local, PLAYER_MANIFEST)):
                die("%s has no %s -- is it a built bundle?" % (local, PLAYER_MANIFEST))
            print("pinning the local bundle at %s" % local)
            stage = local
            with open(os.path.join(local, PLAYER_MANIFEST), encoding="utf-8") as f:
                pin = json.load(f)
            channel = "local"
        else:
            tag = PLAYER_CHANNELS[channel]
            base = "https://github.com/%s/releases/download/%s/" % (PLAYER_REPO, tag)
            print("fetching %s (%s)" % (tag, channel))
            man_path = os.path.join(tmp, PLAYER_MANIFEST)
            urllib.request.urlretrieve(base + PLAYER_MANIFEST, man_path)
            with open(man_path, encoding="utf-8") as f:
                pin = json.load(f)
        src = pin.get("source", {})
        print("  %s @ %s (%s)" % (pin.get("bundle", "?"), (src.get("commit") or "?")[:12],
                                  src.get("branch", "?")))
        if src.get("dirty"):
            # The artifact corresponds to no commit, so the sha above cannot be
            # used to reproduce it or to review what went into it.
            die("that build came from a dirty tree; refusing to pin it")

        if not local:
            tgz = os.path.join(tmp, PLAYER_ASSET)
            urllib.request.urlretrieve(base + PLAYER_ASSET, tgz)
            stage = os.path.join(tmp, "stage")
            os.makedirs(stage)
            with tarfile.open(tgz) as tf:
                for m in tf.getmembers():
                    # A release asset is remote input: refuse paths, links and
                    # anything that is not a plain file before it touches disk.
                    if not m.isfile() or "/" in m.name.lstrip("./") or m.name.startswith("/"):
                        if m.name not in (".", "./"):
                            die("unexpected entry in the release archive: %r" % m.name)
                        continue
                    tf.extract(m, stage)

        bad = _verify(pin, stage, label="")
        if bad:
            for b in bad:
                print("  %s" % b)
            die("the downloaded bundle does not match its own manifest")
        print("  %d files, all hashes verified" % len(pin.get("files", {})))

        old = _pin()
        for name in sorted(pin["files"]):
            shutil.copy(os.path.join(stage, name), os.path.join(RUNNER, name))
        # Drop files the previous pin had and this one does not, so the bundle
        # is what the manifest says rather than a union of every version ever.
        if old:
            for name in old.get("files", {}):
                if name not in pin["files"]:
                    stale = os.path.join(RUNNER, name)
                    if os.path.isfile(stale):
                        os.remove(stale)
                        print("  removed %s (not in this bundle)" % name)
        pin["channel"] = channel
        with open(os.path.join(RUNNER, VERSION_FILE), "w",
                  encoding="utf-8", newline="\n") as f:
            json.dump(pin, f, indent=2, sort_keys=True)
            f.write("\n")
        print("runner/ updated; %s written" % VERSION_FILE)
        print("  commit the diff -- that is the review")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def cmd_conform(args):
    """Run the conformance suite (SPEC.md 11)."""
    sys.path.insert(0, HERE)
    from conformance import run as _run
    sys.exit(_run.main(args))


def main():
    cmds = {"new": cmd_new, "run": cmd_run, "export": cmd_export,
            "port": cmd_port, "demo": cmd_demo,
            "check": cmd_check, "pack": cmd_pack, "unpack": cmd_unpack,
            "gfx": cmd_gfx, "map": cmd_map, "conform": cmd_conform,
            "player": cmd_player}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(__doc__.strip())
        sys.exit(0 if len(sys.argv) < 2 else 1)
    cmds[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
