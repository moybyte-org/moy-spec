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
    moy.py export <cart.moy>     the publishable web bundle: ~300KB of static
                                 files that boot straight into the game --
                                 host anywhere (itch.io HTML5 uploads work)
    moy.py port <cart.p8|url>    convert a PICO-8 cart: assets via p8_import,
             [--title NAME]      code mechanically ported to Lua 5.4 under the
             [--zoom]            p8 compat shim (p8_lua_port). The cart draws
                                 native 128x128 (manifest canvas, SPEC.md 3.1);
                                 --zoom adds the view(128,120) hint so 4:3
                                 hosts fill their height (SPEC.md 6)
    moy.py demo                  fetch Celeste Classic (PICO-8), port it, play
          [--web]                it in the NATIVE player -- the one-command
                                 show-off. --web (or a port number) opens the
                                 browser player instead, which is also the
                                 fallback where moy-play is not built

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
          [--build]              its files still match; --build recompiles it
                                 from libmoy (needs emscripten -- nothing else
                                 here does)
    moy.py play <cart.moy>       run the cart in the NATIVE desktop player
                                 (moy-play, the C console -- ships beside moy
                                 in the release download). `run` is the dev
                                 loop in the browser; `play` is just playing
    moy.py push <cart.moy>       copy the cart onto a connected console --
          [--to <where>]         a volume with a moy-console.json marker, a
          [--list]               serial port, or http://<console>. Probes per
                                 proposals/sideload.md; --list shows what it
                                 found, --to skips probing (a directory, a
                                 port, or a URL)

Pure Python stdlib, no dependencies. The player it wraps is runner/ -- libmoy
compiled to WebAssembly (see runner/BUILD.md); the spec it implements is
SPEC.md; the console as a library is moycore/.
"""

import http.server
import json
import os
import shutil
import sys
import webbrowser

# Frozen (PyInstaller) or a checkout: HERE is where the data files live. In a
# onefile binary that is the extraction dir (sys._MEIPASS), which vanishes on
# exit -- read-only territory, which _writable_runner below accounts for.
FROZEN = getattr(sys, "frozen", False)
HERE = getattr(sys, "_MEIPASS",
               os.path.dirname(os.path.abspath(__file__)))
PROG = "moy" if FROZEN else "moy.py"


def _user_runner():
    """A per-user override for the player, when frozen: a data dir the user can
    drop their own build into. The bundled runner/ ships with every moy release
    and is what almost everyone gets; this dir exists only if someone building
    the player themselves wants their build used, and then wins."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA",
                              os.path.expanduser("~\\AppData\\Local"))
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME",
                              os.path.expanduser("~/.local/share"))
    return os.path.join(base, "moy", "runner")


def _pick_runner():
    bundled = os.path.join(HERE, "runner")
    if not FROZEN:
        return bundled
    user = _user_runner()
    if os.path.isfile(os.path.join(user, "VERSION")):
        return user
    return bundled


RUNNER = _pick_runner()
# Which files the player bundle contains is the BUILD's business, not this
# CLI's -- it grew a worker.js once, and lost it again when the console stopped
# being an interpreter. So the stamp (runner/VERSION) is authoritative, and an
# unstamped runner/ is read from disk rather than guessed at. These are the
# files in runner/ that belong to THIS repository rather than to the player,
# and are never exported.
VERSION_FILE = "VERSION"
# The licence notice is the one file in runner/ that is neither the player nor
# this repository's documentation of it: it must SHIP with an export. moy.wasm has
# Lua and Emscripten's runtime compiled in, both MIT, and MIT requires the notice
# to accompany every copy -- so an export that carried only the four player files
# was distributing them stripped. It is not part of the build and not stamped,
# hence its place in the set below as well.
LICENSE_FILE = "LICENSE.txt"
RUNNER_NOT_PLAYER = frozenset((VERSION_FILE, "BUILD.md", "THIRD_PARTY.md",
                               LICENSE_FILE))

# The player is built HERE, from libmoy: `libmoy/port/wasm/build.sh` compiles
# the same C console an ESP32 links, through emscripten, into runner/. It used
# to be vendored from the reference implementation's MicroPython build and
# pinned by hash, which made the spec's own player a downstream artifact of one
# implementation -- and shipped an 825 KB interpreter to run a Lua cart.
PLAYER_BUILD = os.path.join("libmoy", "port", "wasm", "build.sh")
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
    notice = os.path.join(RUNNER, LICENSE_FILE)
    if os.path.isfile(notice):
        shutil.copy(notice, os.path.join(out, LICENSE_FILE))
    with open(os.path.join(out, "carts.json"), "w", encoding="utf-8") as f:
        json.dump(pack_cart(src), f)
    print("exported -> %s" % out)
    print("  static files: host anywhere, or zip the folder for itch.io (HTML5)")
    print("  %s covers the player; your cart's own licence is yours" % LICENSE_FILE)


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
    title = None
    if "--title" in args and args.index("--title") + 1 < len(args):
        title = args[args.index("--title") + 1]
    args = [a for a in args if not a.startswith("--")]
    if title is not None:     # drop the value that followed --title
        args = [a for a in args if a != title]
    if crop != (0, 0):        # drop the "T,B" that followed --zoom
        args = [a for a in args if not ("," in a and a.replace(",", "").isdigit())]
    if not args:
        die("usage: moy.py port <cart.p8 | url> [out.moy]"
            " [--title NAME] [--zoom [T,B]]")
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
    p8_lua_port.port(src, out, title=title, crop=crop)
    print("ported -> %s" % out)
    print("  PICO-8 carts carry their own licenses (BBS default CC BY-NC-SA")
    print("  4.0) -- ported carts are dev/personal material unless stated.")
    print("  next: %s run %s" % (sys.argv[0], os.path.relpath(out)))


def cmd_demo(args):
    """Fetch + port + play Celeste Classic -- the one-command demo.

    It plays in the NATIVE player when there is one. `run` opens a browser
    because a browser is where hot reload lives, and that is the dev loop --
    but `demo` is not a dev loop, it is a game, and a desktop program that
    answers by opening a browser tab is a surprise nobody asked for. So the
    window is the default and the tab is the fallback, which is also the only
    honest order: the fallback is what a checkout without `make play` has.
    """
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

    # A port number only means something to the web player, so passing one is
    # asking for it -- otherwise `demo 8081` would go native and drop the 8081
    # on the floor.
    web = "--web" in args or any(a.isdigit() for a in rest)
    rest = [a for a in rest if a != "--web"]
    found, looked = _native_player()
    if web or found is None:
        if not web:
            print("no moy-play here (looked for %s)" % ", ".join(looked))
            print("  playing in the browser instead; %s" % (
                "it ships beside moy in the release download" if FROZEN
                else "`make play` in libmoy/ builds the native one"))
        cmd_run(["celeste.moy"] + rest)
    else:
        print("playing in the native player (%s play, --web for the browser)"
              % PROG)
        cmd_play(["celeste.moy"])


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

    # `check` ANALYSES a cart; it does not host one. It grants whatever the
    # manifest declares so SPEC.md 10's capability gate never fires here -- a
    # cart no host can run is a FINDING, with a line to change, and refusing to
    # load it would hide that behind "FAILS TO LOAD".
    declared = []
    try:
        ext = json.loads(files["manifest.json"]).get("extensions")
        if isinstance(ext, (list, tuple)):
            declared = [e for e in ext if isinstance(e, str)]
    except (KeyError, ValueError, AttributeError):
        pass

    try:
        cart = moycore.Cart.from_files(files, supported_extensions=tuple(declared))
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
        moycore.Cart.from_files(files)
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
                "Rebuild it with `%s player --build`."
                % (", ".join(missing), VERSION_FILE, PROG))
        return tuple(want)
    # Unpinned: the player is whatever is there, minus this repository's own
    # documentation of it.
    if not os.path.isdir(RUNNER):
        die("no runner/ -- build the player with `%s player --build`" % PROG)
    found = tuple(sorted(
        f for f in os.listdir(RUNNER)
        if os.path.isfile(os.path.join(RUNNER, f)) and f not in RUNNER_NOT_PLAYER))
    if not found:
        die("runner/ has no player files -- build it with `%s player --build`" % PROG)
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
    """Show, verify, or rebuild the web player.

    runner/ is a BUILD -- libmoy plus Lua plus port/wasm/main.c through
    emscripten -- and it is checked in so that `run` needs nothing but Python
    and a browser, which is what the README promises. VERSION records which
    build it is (the commit, and a sha256 per file), so "which player is this?"
    has an answer in the tree and a rebuild is an ordinary reviewable diff.

    --build re-runs the build script. That is the only thing here that needs
    emscripten; playing carts never does.
    """
    if "--build" in args:
        if FROZEN:
            die("this is a release binary -- build the player from a checkout")
        script = os.path.join(HERE, PLAYER_BUILD)
        if not os.path.isfile(script):
            die("no %s in this checkout" % PLAYER_BUILD)
        import subprocess
        rc = subprocess.call([script, RUNNER])
        if rc != 0:
            sys.exit(rc)
        print("")
        print("runner/ rebuilt; commit the diff -- that is the review")
        return

    if FROZEN:
        print("player files: %s%s" % (
            RUNNER, "" if RUNNER == _user_runner() else "  (bundled with this build)"))
    pin = _pin()
    if pin is None:
        print("runner/: not stamped (no %s)" % VERSION_FILE)
        print("  `%s player --build` rebuilds it and writes one" % PROG)
        return
    src = pin.get("source", {})
    print("runner/: %s" % pin.get("bundle", "?"))
    print("  built from  %s%s" % ((src.get("commit") or "?")[:12],
                                  "  (A DIRTY TREE)" if src.get("dirty") else ""))
    if src.get("branch"):
        print("  branch      %s" % src["branch"])
    if pin.get("toolchain"):
        print("  toolchain   %s" % pin["toolchain"])
    bad = _verify(pin, RUNNER)
    for b in bad:
        print("  MISMATCH %s" % b)
    print("  %d files, %s" % (len(pin.get("files", {})),
                              "all match the stamp" if not bad else "SEE ABOVE"))
    if bad:
        sys.exit(1)


def cmd_conform(args):
    """Run the conformance suite (SPEC.md 11)."""
    sys.path.insert(0, HERE)
    from conformance import run as _run
    sys.exit(_run.main(args))


def _native_player():
    """(path, where-we-looked) for moy-play, path None when it is not there.

    moy-play is the C console (libmoy) with its SDL2 port -- a sibling binary,
    not something this CLI contains. The lookup order is where it actually is:
    beside this executable in a release download, or libmoy's build dir in a
    checkout. It returns rather than dies because `demo` asks a question of it
    ("is there one?") that `play` does not."""
    exe = "moy-play.exe" if sys.platform == "win32" else "moy-play"
    if FROZEN:
        looked = [os.path.join(
            os.path.dirname(os.path.abspath(sys.executable)), exe)]
    else:
        looked = [os.path.join(HERE, "libmoy", "build", exe)]
    return next((c for c in looked if os.path.isfile(c)), None), looked


def cmd_play(args):
    """Run a cart in the native desktop player."""
    if not args:
        die("usage: %s play <cart.moy>" % PROG)
    src = cart_dir(args[0])
    if not os.path.isdir(src):
        die("no such cart: " + src)
    found, looked = _native_player()
    if found is None:
        hint = ("it ships beside moy in the release download" if FROZEN
                else "`make play` in libmoy/ builds it")
        die("moy-play not found (looked for %s) -- %s"
            % (", ".join(looked), hint))
    import subprocess
    sys.exit(subprocess.call([found, src]))


def cmd_push(args):
    """Copy a cart onto a connected console (proposals/sideload.md)."""
    sys.path.insert(0, HERE)
    import sideload

    if "--list" in args:
        consoles, notes = sideload.probe()
        for c in consoles:
            print("  %s" % c)
        for n in notes:
            print("  %s" % n)
        if not consoles:
            print("no moy console found -- a console advertises itself per "
                  "proposals/sideload.md")
            sys.exit(1)
        return

    if not args:
        die("usage: %s push <cart.moy> [--to <volume|port|url>] [--list]" % PROG)
    src = cart_dir(args[0])
    if not os.path.isdir(src):
        die("no such cart: " + src)

    # Refuse to push a cart that does not load -- same bar as `pack`. The
    # worst place to discover a broken manifest is on the handheld.
    moycore = _moycore()
    from moycore import pack as _pack
    files = _pack.read_folder(src)
    files.pop("moy-api.lua", None)
    try:
        moycore.Cart.from_files(files)
    except moycore.CartError as exc:
        die("refusing to push a cart that does not load: %s" % exc)

    try:
        if "--to" in args:
            console = sideload.target_console(args[args.index("--to") + 1])
        else:
            consoles, notes = sideload.probe()
            if not consoles:
                print("moy: no moy console found", file=sys.stderr)
                for n in notes:
                    print("  %s" % n, file=sys.stderr)
                print("a console advertises itself per proposals/sideload.md; "
                      "--to <dir|port|url> targets one directly", file=sys.stderr)
                sys.exit(1)
            if len(consoles) > 1:
                for c in consoles:
                    print("  %s" % c, file=sys.stderr)
                die("%d consoles found -- pick one with --to" % len(consoles))
            console = consoles[0]
        print("pushing to %s" % console)
        sideload.push(console, src)
    except sideload.SideloadError as exc:
        die(str(exc))


def main():
    cmds = {"new": cmd_new, "run": cmd_run, "export": cmd_export,
            "port": cmd_port, "demo": cmd_demo,
            "check": cmd_check, "pack": cmd_pack, "unpack": cmd_unpack,
            "gfx": cmd_gfx, "map": cmd_map, "conform": cmd_conform,
            "player": cmd_player, "push": cmd_push, "play": cmd_play}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(__doc__.strip().replace("moy.py ", PROG + " "))
        sys.exit(0 if len(sys.argv) < 2 else 1)
    cmds[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
