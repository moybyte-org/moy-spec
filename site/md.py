"""A small Markdown -> HTML converter, stdlib only.

Deliberately not a dependency. This repo's whole claim is "Python 3.8+ and a
browser, nothing else"; a site build that needed a package index (let alone a
node toolchain) would contradict the thing it is publishing. So this handles
exactly the Markdown the canonical documents use -- ATX headings, fenced code,
GFM pipe tables, blockquotes, lists, rules, paragraphs, and inline
code/bold/italic/links/bare URLs -- and nothing else.

Two behaviours here are not Markdown, and are the reason the spec reads well on
the web:

  * Section references become links. The spec text is dense with them and
    following one by hand means scrolling to find it.
  * An inline code span holding a six-digit hex colour gets a swatch, so the
    palette table shows its colours.

Nothing is written back to the source documents; this only affects rendering.
"""

import html
import re

__all__ = ["render", "inline", "plain", "slug", "cells", "Rendered", "DELIM"]

SECTION = "§"          # the section sign, kept out of the source encoding


# --- inline -----------------------------------------------------------------

INLINE = re.compile(
    r"`(?P<code>[^`\n]+)`"
    r"|\[(?P<ltext>[^\]\n]*)\]\((?P<lhref>[^)\s]+)\)"
    r"|\*\*(?=\S)(?P<b>[^\n]+?)(?<=\S)\*\*"
    r"|\*(?=\S)(?P<i>[^*\n]+?)(?<=\S)\*"
    r"|(?P<url>https?://[^\s<>()\[\]]+)"
    r"|" + SECTION + r"(?P<sec>\d+(?:\.\d+)?)"
)

HEX = re.compile(r"^[0-9A-F]{6}$")


def _code(text):
    """An inline code span. Six-digit hex colours carry a swatch."""
    esc = html.escape(text)
    if HEX.match(text) and (text == "000000" or any(c.isalpha() for c in text)):
        return ('<code class="hex"><i style="background:#%s"></i>%s</code>'
                % (text, esc))
    return "<code>%s</code>" % esc


def inline(text, ctx):
    """Render one line's inline markup. Recurses through emphasis."""
    out, pos = [], 0
    for m in INLINE.finditer(text):
        out.append(html.escape(text[pos:m.start()]))
        pos = m.end()
        if m.group("code") is not None:
            out.append(_code(m.group("code")))
        elif m.group("ltext") is not None:
            href = ctx.link(m.group("lhref"))
            out.append('<a href="%s">%s</a>'
                       % (html.escape(href, quote=True),
                          inline(m.group("ltext"), ctx)))
        elif m.group("b") is not None:
            out.append("<strong>%s</strong>" % inline(m.group("b"), ctx))
        elif m.group("i") is not None:
            out.append("<em>%s</em>" % inline(m.group("i"), ctx))
        elif m.group("url") is not None:
            url = m.group("url").rstrip(".,;:")
            tail = m.group("url")[len(url):]
            out.append('<a href="%s">%s</a>' % (html.escape(url, quote=True),
                                                html.escape(url)))
            out.append(html.escape(tail))
        else:
            num = m.group("sec")
            target = ctx.section(num)
            label = html.escape(SECTION + num)
            out.append('<a class="sref" href="%s">%s</a>'
                       % (html.escape(target, quote=True), label) if target
                       else label)
    out.append(html.escape(text[pos:]))
    return "".join(out)


def plain(text):
    """Markup stripped -- for headings' ids and the table of contents."""
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = text.replace("**", "").replace("*", "")
    return text.strip()


def slug(text):
    """GitHub's heading slug, so links minted off the rendered .md still land."""
    s = plain(text).lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE)
    return re.sub(r"\s+", "-", s).strip("-")


# --- code highlighting ------------------------------------------------------

LUA_KW = {"and", "break", "do", "else", "elseif", "end", "false", "for",
          "function", "goto", "if", "in", "local", "nil", "not", "or",
          "repeat", "return", "then", "true", "until", "while"}

LUA = re.compile(r"(?P<c>--[^\n]*)"
                 r"|(?P<s>\"[^\"\n]*\"|'[^'\n]*')"
                 r"|(?P<n>\b\d+\.?\d*\b)"
                 r"|(?P<w>[A-Za-z_]\w*)")

JSON = re.compile(r"(?P<k>\"(?:[^\"\\]|\\.)*\")(?=\s*:)"
                  r"|(?P<s>\"(?:[^\"\\]|\\.)*\")"
                  r"|(?P<n>-?\b\d+\.?\d*\b)"
                  r"|(?P<b>\b(?:true|false|null)\b)")


def _hl(code, lang):
    """A conservative tokeniser -- comments, strings, numbers, keywords."""
    pat = {"lua": LUA, "json": JSON}.get(lang)
    if not pat:
        return html.escape(code)
    out, pos = [], 0
    for m in pat.finditer(code):
        out.append(html.escape(code[pos:m.start()]))
        pos = m.end()
        tok = m.group(0)
        if m.lastgroup == "w":
            cls = "kw" if tok in LUA_KW else None
        else:
            cls = {"c": "cm", "s": "st", "k": "ky", "n": "nu", "b": "kw"}[m.lastgroup]
        out.append('<span class="%s">%s</span>' % (cls, html.escape(tok))
                   if cls else html.escape(tok))
    out.append(html.escape(code[pos:]))
    return "".join(out)


# --- blocks -----------------------------------------------------------------

H = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE = re.compile(r"^```\s*(\w*)\s*$")
HR = re.compile(r"^(?:-{3,}|\*{3,}|_{3,})\s*$")
UL = re.compile(r"^[-*]\s+(.*)$")
OL = re.compile(r"^(\d+)\.\s+(.*)$")
DELIM = re.compile(r"^\|?[\s:|-]+\|[\s:|-]*$")
NUMBERED = re.compile(r"^(\d+(?:\.\d+)?)\.?\s")


class Rendered:
    def __init__(self, html, toc, sections, title):
        self.html = html          # the body markup
        self.toc = toc            # [(level, id, text)]
        self.sections = sections  # {"6.1": "id"} for SS-reference linking
        self.title = title        # the document's h1, markup stripped


def cells(row):
    """Split a table row on pipes that are not inside a code span."""
    out, cur, tick = [], [], False
    for ch in row:
        if ch == "`":
            tick = not tick
        if ch == "|" and not tick:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    if out and not out[0].strip():
        out = out[1:]
    if out and not out[-1].strip():
        out = out[:-1]
    return [c.strip() for c in out]


TASK = re.compile(r"^\[([ xX])\]\s+")


def list_item(text, ctx):
    """One <li>, honouring GitHub's task-list syntax.

    A checklist is a checklist wherever it is read, and rendering it as the
    literal characters "[ ]" reads as a typo rather than as a box."""
    m = TASK.match(text)
    if not m:
        return "<li>%s</li>" % inline(text, ctx)
    checked = " checked" if m.group(1) != " " else ""
    return ('<li class="task"><input type="checkbox" disabled%s> %s</li>'
            % (checked, inline(text[m.end():], ctx)))


def render(text, ctx):
    lines = text.replace("\r\n", "\n").expandtabs(4).split("\n")
    out, toc, sections, title = [], [], {}, ""
    i, n = 0, len(lines)
    seen = {}

    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        m = H.match(line)
        if m:
            lvl, raw = len(m.group(1)), m.group(2)
            sid = slug(raw) or "s%d" % i
            if sid in seen:
                seen[sid] += 1
                sid = "%s-%d" % (sid, seen[sid])
            else:
                seen[sid] = 0
            num = NUMBERED.match(plain(raw))
            extra = ""
            if num:
                sections[num.group(1)] = sid
                extra = '<a id="s%s"></a>' % num.group(1).replace(".", "-")
            if lvl == 1 and not title:
                title = plain(raw)
            if lvl >= 2:
                toc.append((lvl, sid, plain(raw)))
            out.append('%s<h%d id="%s">%s<a class="anchor" href="#%s" '
                       'aria-label="link to this section">#</a></h%d>'
                       % (extra, lvl, sid, inline(raw, ctx), sid, lvl))
            i += 1
            continue

        m = FENCE.match(line)
        if m:
            lang = m.group(1)
            i += 1
            buf = []
            while i < n and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            body = _hl("\n".join(buf), lang)
            label = ('<span class="lang">%s</span>' % html.escape(lang)) if lang else ""
            out.append('<div class="code">%s<pre><code>%s</code></pre></div>'
                       % (label, body))
            continue

        if HR.match(line):
            out.append("<hr>")
            i += 1
            continue

        if line.startswith(">"):
            buf = []
            while i < n and lines[i].startswith(">"):
                buf.append(lines[i][1:].lstrip(" "))
                i += 1
            inner = render("\n".join(buf), ctx)
            out.append("<blockquote>%s</blockquote>" % inner.html)
            continue

        # table: a header row followed by a delimiter row
        if "|" in line and i + 1 < n and DELIM.match(lines[i + 1]):
            head = cells(line)
            aligns = []
            for c in cells(lines[i + 1]):
                aligns.append("center" if c.startswith(":") and c.endswith(":")
                              else "right" if c.endswith(":") else "")
            i += 2
            rows = []
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(cells(lines[i]))
                i += 1

            def cell(tag, txt, j):
                a = aligns[j] if j < len(aligns) else ""
                sty = ' style="text-align:%s"' % a if a else ""
                return "<%s%s>%s</%s>" % (tag, sty, inline(txt, ctx), tag)

            th = "".join(cell("th", c, j) for j, c in enumerate(head))
            body = []
            for r in rows:
                # a row of empty cells is a spacer in these documents
                cls = ' class="spacer"' if not any(c for c in r) else ""
                body.append("<tr%s>%s</tr>"
                            % (cls, "".join(cell("td", c, j)
                                            for j, c in enumerate(r))))
            out.append('<div class="tablewrap"><table><thead><tr>%s</tr></thead>'
                       "<tbody>%s</tbody></table></div>" % (th, "".join(body)))
            continue

        if UL.match(line) or OL.match(line):
            ordered = bool(OL.match(line))
            start = OL.match(line).group(1) if ordered else None
            items, cur = [], None
            while i < n:
                ln = lines[i]
                if not ln.strip():
                    # a blank line only ends the list if what follows is not
                    # another item of it (these documents have loose lists)
                    j = i + 1
                    while j < n and not lines[j].strip():
                        j += 1
                    if j >= n or not (OL.match(lines[j]) if ordered
                                      else UL.match(lines[j])):
                        break
                    i = j
                    continue
                m2 = OL.match(ln) if ordered else UL.match(ln)
                if m2:
                    if cur is not None:
                        items.append(" ".join(cur))
                    cur = [m2.group(2) if ordered else m2.group(1)]
                elif ln.startswith(" ") and cur is not None:
                    cur.append(ln.strip())
                else:
                    break
                i += 1
            if cur is not None:
                items.append(" ".join(cur))
            tag = "ol" if ordered else "ul"
            attr = ' start="%s"' % start if ordered and start != "1" else ""
            out.append("<%s%s>%s</%s>"
                       % (tag, attr, "".join(list_item(it, ctx) for it in items),
                          tag))
            continue

        # paragraph
        buf = []
        while i < n and lines[i].strip():
            ln = lines[i]
            if buf and (H.match(ln) or FENCE.match(ln) or HR.match(ln)
                        or ln.startswith(">") or UL.match(ln) or OL.match(ln)):
                break
            buf.append(ln.strip())
            i += 1
        out.append("<p>%s</p>" % inline(" ".join(buf), ctx))

    return Rendered("\n".join(out), toc, sections, title)
