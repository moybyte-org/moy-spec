"""Static checks a cart author can run without owning the hardware.

The gap this closes: today the only way to learn that a cart overruns SPEC.md
1.1's floor, reaches past the SPEC.md 4.1 sandbox, or uses a verb it never
declared, is to run it on the tightest conforming console. Most authors will
never own one. So a cart ships, and the failure surfaces on somebody else's
handheld, which is the worst possible place for it.

Everything here is decidable from the cart's own bytes. Anything that is not --
whether the Lua heap fits at level 7, whether the game is FUN with buttons
alone -- is reported as a signal and labelled as one. A check that guesses and
states its guess as a verdict is worse than no check.

Findings are (level, code, message):
  error  this cart is not conforming; a strict host may refuse it
  warn   it will run, but not everywhere, or not as the author intended
  info   worth knowing
"""

from . import budget
from . import palette as _palette
from .cart import FORMAT, VALID_FPS, INPUT_KINDS, ICON_MAX_TILES
from .sheet import MAP_MAX, TILE_COUNT

# SPEC.md 4.1: the available Lua standard library is EXACTLY base (minus these),
# math, string, table. "This is a maximum, not a suggestion."
FORBIDDEN_GLOBALS = (
    "io", "os", "debug", "package", "coroutine",
    "load", "loadstring", "dofile", "require", "collectgarbage",
)

# SPEC.md 6.1 -- provisional, explicitly not part of core 0.1. The batch verbs
# that used to sit alongside these were deleted from the spec (6.1 records the
# measurements); a cart using one now names an unknown verb, not a provisional one.
PROVISIONAL_VERBS = ("tri", "trib", "sspr", "tline")

# SPEC.md 10 standard extensions, and the verbs each one grants.
EXTENSION_VERBS = {
    "layers": ("make_layer", "draw_layer", "background"),
    "viewport": ("view",),
}

TOUCH_VERBS = ("touch",)
KEYBOARD_VERBS = ("key", "keyp", "textmode")
BUTTON_VERBS = ("btn", "btnp")


def strip_lua(src):
    """Source with comments and string literals blanked out.

    Crude but sufficient, and deliberately conservative: identifiers inside
    strings must not trip the sandbox scan (a cart printing the word "os" is
    not reaching for the os library), and a false ERROR is far more expensive
    than a missed one -- an author who is told their fine cart is broken stops
    trusting the tool."""
    out = []
    i = 0
    n = len(src)
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if c == "-" and nxt == "-":
            if src[i + 2:i + 4] == "[[":                # long comment
                end = src.find("]]", i + 4)
                end = n if end < 0 else end + 2
                out.append(" " * (end - i))
                i = end
                continue
            end = src.find("\n", i)
            end = n if end < 0 else end
            out.append(" " * (end - i))
            i = end
            continue
        if c == "[" and nxt == "[":                     # long string
            end = src.find("]]", i + 2)
            end = n if end < 0 else end + 2
            out.append(" " * (end - i))
            i = end
            continue
        if c == '"' or c == "'":
            j = i + 1
            while j < n and src[j] != c:
                j += 2 if src[j] == "\\" else 1
            j = min(j + 1, n)
            out.append(" " * (j - i))
            i = j
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _calls(code, name):
    """Does `code` call the global `name`? Word-boundary match followed by an
    opening paren, so a local variable called `key` is not a keyboard verb."""
    i = 0
    n = len(code)
    ln = len(name)
    while True:
        i = code.find(name, i)
        if i < 0:
            return False
        before = code[i - 1] if i else " "
        after = code[i + ln:i + ln + 1]
        j = i + ln
        while j < n and code[j] in " \t":
            j += 1
        opens = j < n and code[j] in "(\"'{"
        if not (before.isalnum() or before == "_" or before == ".") \
                and not (after.isalnum() or after == "_") and opens:
            return True
        i += ln


def check_manifest(manifest, findings):
    if manifest.get("format") != FORMAT:
        findings.append(("error", "manifest.format",
                         'format is %r, must be "%s" (SPEC.md 3.1)'
                         % (manifest.get("format"), FORMAT)))
    if not manifest.get("title"):
        findings.append(("error", "manifest.title",
                         "title is required (SPEC.md 3.1)"))
    fps = manifest.get("fps", 30)
    if fps not in VALID_FPS:
        findings.append(("error", "manifest.fps",
                         "fps is %r; SPEC.md 5 allows 30 or 60 only" % (fps,)))
    rt = manifest.get("runtime")
    if rt is not None and rt != "lua":
        findings.append(("warn", "manifest.runtime",
                         'runtime is "%s"; Lua is core\'s only binding, so this cart is '
                         "non-portable by construction and every other console will "
                         "refuse it cleanly (SPEC.md 15)" % rt))
    kinds = manifest.get("input")
    if kinds is not None:
        if not isinstance(kinds, (list, tuple)):
            findings.append(("warn", "manifest.input",
                             "input should be an array of %s" % ", ".join(INPUT_KINDS)))
        else:
            for k in kinds:
                if k not in INPUT_KINDS:
                    findings.append(("warn", "manifest.input",
                                     "unknown input kind %r (hosts ignore it)" % (k,)))
    pal = manifest.get("palette")
    if pal is not None:
        try:
            _palette.parse(pal)
        except Exception as exc:
            findings.append(("error", "manifest.palette", str(exc)))
    icon = manifest.get("icon")
    if icon is not None:
        ok = False
        try:
            if isinstance(icon, (list, tuple)) and len(icon) == 3:
                t, w, h = int(icon[0]), int(icon[1]), int(icon[2])
                ok = 1 <= w <= ICON_MAX_TILES and 1 <= h <= ICON_MAX_TILES \
                    and 0 <= t < TILE_COUNT
            else:
                t = int(icon)
                ok = 0 <= t < TILE_COUNT
        except (TypeError, ValueError):
            ok = False
        if not ok:
            findings.append(("warn", "manifest.icon",
                             "icon is out of range and will be ignored; the host will "
                             "pick a picture for you (SPEC.md 3.4)"))


def check_source(source, manifest, findings):
    code = strip_lua(source)

    for name in FORBIDDEN_GLOBALS:
        if _calls(code, name) or (name in ("io", "os", "debug", "package", "coroutine")
                                  and (name + ".") in code):
            findings.append(("error", "sandbox",
                             "the cart reaches for `%s`, which SPEC.md 4.1 puts outside "
                             "the sandbox; this must fail on every conforming host" % name))

    declared = manifest.get("extensions") or []
    for ext in EXTENSION_VERBS:
        used = [v for v in EXTENSION_VERBS[ext] if _calls(code, v)]
        if used and ext not in declared:
            # Opportunistic use is legitimate and different from a missing
            # declaration: a cart that checks the verb exists before calling
            # it runs everywhere, degraded where the extension is absent.
            # Declaring would make those hosts refuse a cart that works.
            guarded = all(("%s ~= nil" % v) in code or ("nil ~= %s" % v) in code
                          or ("type(%s)" % v) in code for v in used)
            if guarded:
                findings.append(("info", "extensions",
                                 "uses %s behind an existence check without declaring "
                                 '"%s" -- optional use: hosts without the extension '
                                 "run the cart degraded (SPEC.md 10)"
                                 % (", ".join(used), ext)))
            else:
                findings.append(("error", "extensions",
                                 "the cart calls %s but does not declare \"%s\" in "
                                 "extensions; a host without it cannot refuse the cart "
                                 "cleanly and will crash partway in (SPEC.md 10)"
                                 % (", ".join(used), ext)))
    for ext in declared:
        if ext in EXTENSION_VERBS:
            if not any(_calls(code, v) for v in EXTENSION_VERBS[ext]):
                findings.append(("warn", "extensions",
                                 'declares "%s" but never uses it; every console '
                                 "without that extension refuses this cart for nothing"
                                 % ext))
        elif "." not in ext:
            findings.append(("warn", "extensions",
                             '"%s" is neither a standard extension nor namespaced; '
                             "a vendor extension MUST be vendor.feature so it can never "
                             "collide with a future standard one (SPEC.md 10)" % ext))

    used_prov = [v for v in PROVISIONAL_VERBS if _calls(code, v)]
    if used_prov:
        findings.append(("warn", "provisional",
                         "uses %s, which SPEC.md 6.1 marks provisional and excludes "
                         "from core 0.1 until its promotion gates clear; semantics "
                         "are frozen but a host may not implement it yet"
                         % ", ".join(used_prov)))

    # Declared input vs what the script actually reads. Advisory in both
    # directions -- SPEC.md 7.3 makes the field a hint for drawing soft
    # controls, never a requirement.
    kinds = manifest.get("input")
    uses_touch = any(_calls(code, v) for v in TOUCH_VERBS)
    uses_kbd = any(_calls(code, v) for v in KEYBOARD_VERBS)
    uses_btn = any(_calls(code, v) for v in BUTTON_VERBS)
    if isinstance(kinds, (list, tuple)):
        if uses_touch and "touch" not in kinds:
            findings.append(("warn", "input", "calls touch() but does not list \"touch\""))
        if uses_kbd and "keyboard" not in kinds:
            findings.append(("warn", "input", "reads the keyboard but does not list \"keyboard\""))
        if uses_btn and "buttons" not in kinds:
            findings.append(("warn", "input", "reads buttons but does not list \"buttons\""))
        if "touch" in kinds and not uses_touch:
            findings.append(("info", "input",
                             'lists "touch" but never calls touch(); a host may draw soft '
                             "controls this cart does not need"))

    # SPEC.md 7.3: "A cart MUST be playable with buttons alone."  Not decidable
    # -- but a cart that never reads a button at all cannot be, and that IS.
    if (uses_touch or uses_kbd) and not uses_btn:
        findings.append(("error", "buttons-alone",
                         "the cart reads touch/keyboard but never reads a button, so it "
                         "cannot be played on a six-button device; SPEC.md 7.3 makes that "
                         "non-conforming (touch and keyboard are enhancements)"))

    if _calls(code, "textmode") and not _calls(code, "quit"):
        findings.append(("error", "textmode",
                         "calls textmode() but never quit(); while a cart holds text mode "
                         "the host's own exit gesture may be unreachable, so SPEC.md 7.3 "
                         "requires such a cart to offer its own exit"))


def check_cart(cart, files=None, findings=None):
    """Every static check, against a loaded Cart.

    `files` is the raw {name: bytes} map when available, which lets the size
    report be about the real file rather than a re-serialization."""
    findings = [] if findings is None else findings
    check_manifest(cart.manifest, findings)
    check_source(cart.source, cart.manifest, findings)

    tm = cart.tilemap
    if tm.w > MAP_MAX or tm.h > MAP_MAX:
        findings.append(("error", "map.size",
                         "map is %dx%d; SPEC.md 3.3 caps each dimension at %d and a host "
                         "MUST reject a larger one rather than allocate past its budget"
                         % (tm.w, tm.h, MAP_MAX)))
    elif not budget.fits(tm.w, tm.h):
        findings.append(("error", "map.size",
                         "map is %dx%d = %s, past the %s the host reserved (SPEC.md 1.1)"
                         % (tm.w, tm.h, budget.human(tm.w * tm.h),
                            budget.human(budget.TILEMAP_EXACT))))

    # A map cell naming a tile the sheet does not carry draws blank. Legal
    # (SPEC.md 3.2: a short sheet leaves the rest blank) but almost always a
    # mistake, so it is worth saying.
    if not cart.sheet.is_blank():
        highest = -1
        for c in tm.cells:
            if c - 1 > highest:
                highest = c - 1
        if highest >= cart.sheet.count:
            findings.append(("warn", "map.tiles",
                             "the map places tile %d but the sheet holds %d; those cells "
                             "draw blank" % (highest, cart.sheet.count)))

    if files:
        total = 0
        for name in files:
            total += len(files[name])
        findings.append(("info", "size",
                         "cart is %s across %d files (source %s)"
                         % (budget.human(total), len(files),
                            budget.human(len(cart.source.encode("utf-8"))))))
        findings.append(("info", "budget",
                         "fixed allocations: framebuffer %s, sheet %s, map %s of %s; "
                         "cart heap %s is runtime and not decidable from here"
                         % (budget.human(budget.FRAMEBUFFER),
                            budget.human(budget.SPRITE_SHEET),
                            budget.human(budget.tilemap_bytes(tm)),
                            budget.human(budget.TILEMAP),
                            budget.human(budget.CART_HEAP))))
    return findings


def worst(findings):
    for level in ("error", "warn"):
        for f in findings:
            if f[0] == level:
                return level
    return "ok"
