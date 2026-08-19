#!/usr/bin/env python3
"""Build the moy-spec website into _site/ -- stdlib only, no build step.

The rule this generator exists to obey: **the canonical documents are the ones
at the repository root, and nothing is ever copied beside them.** SPEC.md,
RATIONALE.md, README.md and the attribution files are read where they live and
rendered to HTML here; palette.json and font.bin -- the two normative data
files -- are read here too, and supply the site's own colours and lettering, so
the page cannot drift from the spec it publishes even in its styling.

The playable demo is built the same way: `moy.py export examples/verbs.moy`
against the vendored runner/, so what a visitor plays is exactly the player
this repository ships, at the commit they are reading.

    python3 site/build.py                 # -> _site/
    python3 site/build.py --out /tmp/x    # somewhere else
    python3 site/build.py --no-demo       # skip the ~690 KB of player bundles

Everything it emits is generated. Do not edit _site/; edit the sources.
"""

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.dont_write_bytecode = True     # no __pycache__ in a source tree this tidy
sys.path.insert(0, HERE)

import md  # noqa: E402  (sibling module, found via the path insert above)

REPO = "https://github.com/moybyte-org/moy-spec"
IMPL = "https://github.com/moybyte-org/moybyte"
BRANCH = "main"
# The playable demos, hero first. A GAME leads (it is what makes a visitor stay);
# the verb tour stays one click away because it doubles as the conformance suite
# seed. Each is exported into its own folder by moy.py, so what you play is the
# player this repo ships.
DEMOS = [
    ("play", "examples/brick_siege.moy", "Brick Siege",
     "a tank game &mdash; arrows drive and aim, Z fires"),
    ("verbs", "examples/verbs.moy", "Every core verb",
     "one screen per verb group &mdash; the conformance tour"),
]
DEMO_CART = DEMOS[0][1]        # the hero, still linked from the prose

# Root markdown that becomes a page. Everything else that is linked resolves to
# GitHub, so no repo-relative link is left dangling.
PAGES = {
    "SPEC.md": ("spec.html", "Spec",
                "moy core 0.1 -- the portable console spec: raster, palette, "
                "verb table and cart format."),
    "RATIONALE.md": ("rationale.html", "Rationale",
                     "Why each fixed number in the moy console spec is what it is."),
    "THIRD_PARTY.md": ("third-party.html", "Third party",
                       "Attribution for the components moy core ships."),
    "runner/BUILD.md": ("runner-build.html", "The web player build",
                        "How the moy web player is built."),
    "runner/THIRD_PARTY.md": ("runner-third-party.html", "Web player attribution",
                              "Third-party components inside the compiled moy web player."),
}

NAV = [("index.html", "Home"), ("spec.html", "Spec"),
       ("rationale.html", "Rationale"), ("index.html#play", "Play")]


# --- palette + font: the spec's own data files drive the design -------------

def load_palette():
    with open(os.path.join(ROOT, "palette.json"), encoding="utf-8") as f:
        pal = json.load(f)
    if len(pal) != 64:
        raise SystemExit("palette.json: expected 64 entries, got %d" % len(pal))
    return ["#" + c for c in pal]


def mix(a, b, t):
    """Blend two #rrggbb colours; t=0 is a, t=1 is b."""
    def ch(c, i):
        return int(c[1 + 2 * i:3 + 2 * i], 16)
    return "#%02x%02x%02x" % tuple(
        round(ch(a, i) * (1 - t) + ch(b, i) * t) for i in range(3))


def load_font():
    with open(os.path.join(ROOT, "font.bin"), "rb") as f:
        data = f.read()
    if len(data) != 96 * 8:
        raise SystemExit("font.bin: expected 768 bytes, got %d" % len(data))
    return data


def pixel_svg(text, font, cls="px"):
    """Render text in the spec's console font (SPEC.md 6) as an inline SVG.

    One byte per column, LSB = top row -- the format the spec fixes, read
    straight out of font.bin, so the site's lettering is the console's.
    """
    cols = []
    for chn in text:
        base = (ord(chn) - 32) * 8
        if base < 0 or base + 8 > len(font):
            base = 0
        cols.extend(font[base:base + 8])
    while cols and cols[-1] == 0:
        cols.pop()
    while cols and cols[0] == 0:
        cols.pop(0)
    w = len(cols)
    d = []
    for y in range(8):
        x = 0
        while x < w:
            if (cols[x] >> y) & 1:
                run = 1
                while x + run < w and (cols[x + run] >> y) & 1:
                    run += 1
                d.append("M%d %dh%dv1h-%dz" % (x, y, run, run))
                x += run
            else:
                x += 1
    return ('<svg class="%s" viewBox="0 0 %d 8" width="%d" height="8" '
            'shape-rendering="crispEdges" aria-hidden="true" focusable="false" '
            'xmlns="http://www.w3.org/2000/svg"><path fill="currentColor" '
            'd="%s"/></svg>' % (cls, w, w, "".join(d)))


def palette_grid(pal):
    """The 64 swatches, index labels legible on both dark and light entries."""
    cells = []
    for i, c in enumerate(pal):
        r, g, b = (int(c[1 + 2 * k:3 + 2 * k], 16) for k in range(3))
        lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
        ink = "#000" if lum > 0.55 else "#fff"
        cells.append('<li style="--c:%s;--t:%s"><span></span><b>%d</b></li>'
                     % (c, ink, i))
    return '<ol class="swatches">%s</ol>' % "".join(cells)


# --- link + section resolution ----------------------------------------------

class Ctx:
    """Resolves markdown links and section references for one rendered page."""

    def __init__(self, page, sections=None):
        self.page = page
        self.sections = sections or {}

    def section(self, num):
        sid = self.sections.get(num)
        if not sid:
            return ""
        return ("#s%s" % num.replace(".", "-") if self.page == "spec.html"
                else "spec.html#s%s" % num.replace(".", "-"))

    def link(self, href):
        if re.match(r"^(?:[a-z]+:|//|#)", href):
            return href
        target, _, frag = href.partition("#")
        frag = "#" + frag if frag else ""
        key = target.lstrip("./")
        if key in PAGES:
            return PAGES[key][0] + frag
        if not target:
            return frag
        disk = os.path.join(ROOT, key)
        kind = "tree" if os.path.isdir(disk) or key.endswith("/") else "blob"
        return "%s/%s/%s/%s%s" % (REPO, kind, BRANCH, key.rstrip("/"), frag)


# --- templates ---------------------------------------------------------------

def tmpl(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


def fill(text, **slots):
    for k, v in slots.items():
        text = text.replace("{{%s}}" % k, v)
    left = re.findall(r"\{\{(\w+)\}\}", text)
    if left:
        raise SystemExit("unfilled template slots: %s" % ", ".join(sorted(set(left))))
    return text


def nav_html(current):
    out = []
    for href, label in NAV:
        cls = ' class="on"' if href == current else ""
        out.append('<a href="%s"%s>%s</a>' % (href, cls, label))
    out.append('<a class="ext" href="%s">GitHub</a>' % REPO)
    return "".join(out)


def toc_html(toc):
    # Two entries are not a table of contents; they are a sidebar full of air.
    if len(toc) < 3:
        return ""
    items = "".join('<li class="l%d"><a href="#%s">%s</a></li>'
                    % (lvl, sid, html.escape(text)) for lvl, sid, text in toc)
    return ('<details class="toc" id="toc" open><summary>Contents</summary>'
            '<nav aria-label="Table of contents"><ol>%s</ol></nav></details>' % items)


def page(shell, *, title, desc, body, nav, cls="", wordmark=""):
    return fill(shell, TITLE=html.escape(title), DESC=html.escape(desc, quote=True),
                BODY=body, NAV=nav, CLASS=cls, WORDMARK=wordmark, REPO=REPO,
                IMPL=IMPL)


# --- the landing page --------------------------------------------------------

CARD = re.compile(r"^\*\*\[(?P<t>[^\]]+)\]\((?P<h>[^)]+)\)\*\*\s+—\s+(?P<d>.*)$")


def split_readme(text):
    """Preamble (before the first h2) and the rest, both raw markdown."""
    m = re.search(r"^## ", text, re.M)
    pre, rest = (text[:m.start()], text[m.start():]) if m else (text, "")
    pre = re.sub(r"^#\s+.*\n", "", pre, count=1)
    return pre.strip(), rest.strip()


def preamble_parts(pre, ctx):
    """Hero pieces out of the README preamble: lede, sub, cards, status."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", pre) if b.strip()]
    lede = sub = status = ""
    cards, spare = [], []
    for b in blocks:
        if b.startswith("- "):
            for line in re.split(r"\n(?=- )", b):
                item = line[2:].replace("\n", " ").strip()
                item = re.sub(r"\s+", " ", item)
                m = CARD.match(item)
                if m:
                    cards.append((m.group("t"), ctx.link(m.group("h")), m.group("d")))
                else:
                    spare.append(item)
        elif b.lower().startswith("status"):
            status = md.render(b, ctx).html
        elif not lede:
            lede = md.render(b, ctx).html
        elif not sub:
            sub = md.render(b, ctx).html
        else:
            spare.append(b)
    cards_html = "".join(
        '<a class="card" href="%s"><h3>%s</h3><p>%s</p></a>'
        % (html.escape(h, quote=True), html.escape(t), md.inline(d, ctx))
        for t, h, d in cards)
    extra = "".join(md.render(b, ctx).html for b in spare)
    return lede, sub, cards_html, status, extra


def table_rows(text, heading):
    """The pipe table under a heading, as a list of raw cell lists."""
    m = re.search(r"^#{1,6}\s+%s\s*$" % re.escape(heading), text, re.M)
    if not m:
        return []
    chunk = text[m.end():]
    nxt = re.search(r"^#{1,6}\s", chunk, re.M)
    if nxt:
        chunk = chunk[:nxt.start()]
    rows = [md.cells(ln) for ln in chunk.split("\n")
            if ln.strip().startswith("|")]
    return [r for r in rows
            if r and not all(set(c) <= set("-: ") for c in r)]


def console_facts(spec, ctx):
    rows = table_rows(spec, "1. The console")
    out = []
    for row in rows:
        if len(row) != 2 or row[0].lower() == "property":
            continue
        out.append("<div><dt>%s</dt><dd>%s</dd></div>"
                   % (md.inline(row[0], ctx), md.inline(row[1], ctx)))
    return '<dl class="facts">%s</dl>' % "".join(out) if out else ""


# --- build -------------------------------------------------------------------

def build(out, demo=True):
    pal = load_palette()
    font = load_font()
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)

    src = {}
    for rel in list(PAGES) + ["README.md"]:
        with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
            src[rel] = f.read()

    # Pass 1: collect the spec's section numbers, so a reference to one links
    # from any page (including this repo's other documents).
    sections = md.render(src["SPEC.md"], Ctx("spec.html")).sections
    shell = tmpl("shell.html")

    for rel, (name, label, desc) in PAGES.items():
        ctx = Ctx(name, sections)
        doc = md.render(src[rel], ctx)
        toc = toc_html(doc.toc)
        body = ('<div class="docpage%s">%s<article class="doc">%s</article></div>'
                % ("" if toc else " solo", toc, doc.html))
        title = doc.title or label
        if "moy" not in title.lower():
            title += " — moy core"
        with open(os.path.join(out, name), "w", encoding="utf-8") as f:
            f.write(page(shell, title=title, desc=desc, body=body,
                         nav=nav_html(name), cls="doc-page",
                         wordmark=pixel_svg("moy", font)))

    # The landing page: assembled from the README, never a copy of it.
    ctx = Ctx("index.html", sections)
    pre, rest = split_readme(src["README.md"])
    lede, sub, cards, status, extra = preamble_parts(pre, ctx)
    home = fill(tmpl("home.html"),
                LEDE=lede, SUB=sub, CARDS=cards, STATUS=status, EXTRA=extra,
                FACTS=console_facts(src["SPEC.md"], ctx),
                PALETTE=palette_grid(pal),
                README=md.render(rest, ctx).html,
                WORDMARK_BIG=pixel_svg("moy", font, cls="px big"),
                CORE=pixel_svg("core 0.1", font, cls="px small"),
                DEMOTABS="\n".join(
                    '      <button class="demotab%s" data-src="%s/" '
                    'data-cart="%s"><b>%s</b><span>%s</span></button>'
                    % (" on" if i == 0 else "", slug, html.escape(cart),
                       label, sub)
                    for i, (slug, cart, label, sub) in enumerate(DEMOS)),
                CART=html.escape(DEMO_CART),
                CARTLINK="%s/tree/%s/%s" % (REPO, BRANCH, DEMO_CART),
                REPO=REPO, IMPL=IMPL)
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(page(shell, title="moy core 0.1 — a portable console spec",
                     desc="A small game console that exists as a spec: 320x240, "
                          "64 colours, Lua carts that play on an ESP32 handheld, "
                          "a PC simulator or a browser tab. Play one now.",
                     body=home, nav=nav_html("index.html"), cls="home",
                     wordmark=pixel_svg("moy", font)))

    # Styles: the palette becomes CSS custom properties, so every colour on the
    # page is a colour the spec defines.
    theme = [":root{"]
    for i, c in enumerate(pal):
        theme.append("--p%d:%s;" % (i, c))
    theme.append("--ink-dark:%s;" % mix(pal[1], "#000000", .84))
    theme.append("--surface-dark:%s;" % mix(pal[1], "#000000", .70))
    theme.append("--raised-dark:%s;" % mix(pal[1], "#000000", .56))
    theme.append("--line-dark:%s;" % mix(pal[1], "#000000", .30))
    theme.append("--paper-light:%s;" % mix(pal[7], "#ffffff", .55))
    theme.append("--surface-light:%s;" % mix(pal[7], "#ffffff", .18))
    theme.append("--card-light:%s;" % mix(pal[7], "#ffffff", .78))
    theme.append("--line-light:%s;" % mix(pal[52], pal[5], .38))
    theme.append("--body-light:%s;" % mix(pal[54], "#000000", .18))
    theme.append("--muted-light:%s;" % mix(pal[51], "#000000", .12))
    theme.append("--link-light:%s;" % mix(pal[12], "#000000", .45))
    theme.append("--accent-light:%s;" % mix(pal[2], "#000000", .08))
    theme.append("--ok-light:%s;" % mix(pal[3], "#000000", .14))
    theme.append("--warn-light:%s;" % mix(pal[8], "#000000", .24))
    theme.append("--wip-light:%s;" % mix(pal[9], "#000000", .34))
    theme.append("}\n")
    with open(os.path.join(out, "style.css"), "w", encoding="utf-8") as f:
        f.write("/* generated by site/build.py from palette.json */\n")
        f.write("".join(theme))
        f.write(tmpl("style.css"))

    with open(os.path.join(out, "favicon.svg"), "w", encoding="utf-8") as f:
        glyph = pixel_svg("m", font)
        inner = re.search(r'd="([^"]*)"', glyph).group(1)
        f.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 12">'
                '<rect width="12" height="12" rx="2" fill="%s"/>'
                '<g transform="translate(2 2)"><path fill="%s" d="%s"/></g></svg>'
                % (pal[1], pal[10], inner))

    # The normative data files travel with the spec (SPEC.md 2, 6).
    for rel in ("palette.json", "font.bin"):
        shutil.copy(os.path.join(ROOT, rel), os.path.join(out, rel))
    with open(os.path.join(out, ".nojekyll"), "w") as f:
        f.write("")

    if demo:
        # What a complete bundle is, taken from the player's own stamp rather
        # than named here: this list was two MicroPython filenames until the
        # player was rebuilt from libmoy, and a constant of stale names checks
        # nothing while looking like it checks everything.
        need = ["index.html", "carts.json"]
        try:
            with open(os.path.join(ROOT, "runner", "VERSION"), encoding="utf-8") as f:
                need += sorted(json.load(f)["files"])
        except (OSError, ValueError, KeyError):
            raise SystemExit("runner/VERSION is missing or unreadable -- "
                             "run `moy.py player --build`")
        for slug, cart, _label, _sub in DEMOS:
            dst = os.path.join(out, slug)
            subprocess.run([sys.executable, os.path.join(ROOT, "moy.py"), "export",
                            os.path.join(ROOT, cart), dst],
                           check=True, cwd=ROOT)
            missing = [n for n in need if not os.path.isfile(os.path.join(dst, n))]
            if missing:
                raise SystemExit("demo bundle %s incomplete: %s"
                                 % (slug, ", ".join(missing)))

    total = sum(os.path.getsize(os.path.join(dp, f))
                for dp, _, fs in os.walk(out) for f in fs)
    print("site: %s (%.0f KB)" % (out, total / 1024))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=os.path.join(ROOT, "_site"))
    ap.add_argument("--no-demo", action="store_true",
                    help="skip the WebAssembly demo bundle (fast iteration)")
    a = ap.parse_args()
    build(os.path.abspath(a.out), demo=not a.no_demo)


if __name__ == "__main__":
    main()
