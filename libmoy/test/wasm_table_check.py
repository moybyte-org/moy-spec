#!/usr/bin/env python3
"""The wasm import table is the verb table, and the C binding is the table.

    python3 test/wasm_table_check.py

proposals/wasm-imports.json is the import table of proposals/wasm-runtime.md,
and three things must agree with it or the "one verb table, two bindings"
claim is prose:

  * its names are exactly the globals libmoy's Lua binding installs (parsed
    from src/moy_lua.c: the VERBS table and open_host_verbs, as the reference
    console's own deny-list test does) plus the binding's own five;
  * src/moy_wasm.c's NativeSymbol array names the same rows, in the same
    order, at the same WAMR signature strings;
  * each row's WAMR string says what its wasm type says, and each row's SPEC
    section exists.

Two of the notes are lists the Lua binding also holds -- the verbs `target`
redirects are the ones a Lua layer answers, and `btn`'s indices are its button
names in order -- so those are held equal too. Run by `make wasm-table`.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIBMOY = os.path.dirname(HERE)
ROOT = os.path.dirname(LIBMOY)

# The imports this binding has and the Lua binding does not: the framebuffer,
# the cart's own files, the receiver a Lua layer method has for free, and the
# sample stream.
WASM_ONLY = {"blit", "blit565", "read", "target", "snd"}

# WAMR signature letter -> wasm value type. '*' and '~' are an i32 pointer and
# the i32 length WAMR bounds-checks it by.
WAMR = {"i": "i32", "I": "i64", "f": "f32", "F": "f64", "*": "i32", "~": "i32",
        "$": "i32"}

FAILS = []


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


def fail(msg):
    FAILS.append(msg)
    print("  FAIL " + msg)


def lua_installed(src):
    """The global names moy_lua.c installs as verbs."""
    head = src.index("static const luaL_Reg VERBS[] = {")
    table = src[head:]
    table = table[:table.index("{NULL, NULL}")]
    names = set(re.findall(r'\{"(\w+)",', table))
    host = src[src.index("static void open_host_verbs"):head]
    # W and H are integers (SPEC.md 9's canvas size), not verbs.
    return names | set(re.findall(r'lua_setglobal\(L, "(\w+)"\)', host))


def lua_block(src, opener):
    block = src[src.index(opener):]
    return block[:block.index("};")]


def c_natives(src):
    block = lua_block(src, "static const NativeSymbol NATIVES[] = {")
    return re.findall(r'\{"(\w+)",\s*FN\(w_(\w+)\),\s*"([^"]*)",\s*NULL\}', block)


def spec_sections():
    ids = set()
    for line in read(ROOT, "SPEC.md").splitlines():
        m = re.match(r"^#{2,3}\s+(\d+(?:\.\d+)?)[.\s—-]", line)
        if m:
            ids.add(m.group(1))
    return ids


def main():
    table = json.loads(read(ROOT, "proposals", "wasm-imports.json"))
    rows = table["imports"]
    names = [r["name"] for r in rows]
    lua = read(LIBMOY, "src", "moy_lua.c")
    wasm_c = read(LIBMOY, "src", "moy_wasm.c")

    if table.get("module") != "moy":
        fail('the table\'s module is %r, not "moy"' % table.get("module"))
    if len(set(names)) != len(names):
        fail("the table names a row twice")

    installed = lua_installed(lua)
    if set(names) - WASM_ONLY != installed:
        fail("the table and the Lua binding disagree: only in the table %s, "
             "only in moy_lua.c %s"
             % (sorted(set(names) - WASM_ONLY - installed),
                sorted(installed - set(names))))
    if not WASM_ONLY <= set(names):
        fail("the table lacks %s" % sorted(WASM_ONLY - set(names)))
    else:
        print("  ok   the table is moy_lua.c's %d verbs and %s"
              % (len(installed), ", ".join(sorted(WASM_ONLY))))

    natives = c_natives(wasm_c)
    for name, fn, _ in natives:
        if fn != name:
            fail("NATIVES binds %s to w_%s" % (name, fn))
    if [n for n, _, _ in natives] != names:
        fail("moy_wasm.c's NATIVES are not the table's rows in its order")
    else:
        print("  ok   moy_wasm.c registers the table's %d rows in order" % len(names))
    by_c = dict((n, sig) for n, _, sig in natives)
    for r in rows:
        if r["name"] in by_c and by_c[r["name"]] != r["wamr"]:
            fail("%s: moy_wasm.c says %s, the table %s"
                 % (r["name"], by_c[r["name"]], r["wamr"]))

    sections = spec_sections()
    for r in rows:
        m = re.match(r"^\((.*)\)(.?)$", r["wamr"])
        if not m:
            fail("%s: %r is not a WAMR signature" % (r["name"], r["wamr"]))
            continue
        params = [WAMR[c] for c in m.group(1)]
        results = [WAMR[c] for c in m.group(2)]
        if params != r["params"] or results != r["results"]:
            fail("%s: the WAMR string %s is not (%s) -> (%s)"
                 % (r["name"], r["wamr"], ", ".join(r["params"]),
                    ", ".join(r["results"])))
        if "~" in m.group(1) and not re.search(r"\*~", m.group(1)):
            fail("%s: a '~' that does not follow a '*'" % r["name"])
        spec = r["spec"]
        if spec != "wasm" and spec.lstrip("§") not in sections:
            fail("%s: SPEC.md has no section %s" % (r["name"], spec))
    print("  ok   every row's WAMR string matches its wasm type")

    target = next(r for r in rows if r["name"] == "target")["notes"]
    listed = set(re.search(r"\(((?:[a-z]+ )+[a-z]+)\)", target).group(1).split())
    layer = set(re.findall(r'\{"(\w+)",', lua_block(lua, "static const luaL_Reg LAYER_VERBS[] = {")))
    if listed != layer:
        fail("target's note lists %s; a Lua layer answers %s"
             % (sorted(listed), sorted(layer)))
    else:
        print("  ok   target redirects exactly the %d verbs a Lua layer answers"
              % len(layer))

    btn = next(r for r in rows if r["name"] == "btn")["notes"]
    order = re.findall(r"(\w+) (\d)", re.search(r"-- (.*?) --", btn).group(1))
    lua_btns = re.findall(r'"(\w+)"', lua_block(lua, "BTN_NAMES[MOY_BTN_COUNT] = {"))
    if [n for n, _ in order] != lua_btns or [int(i) for _, i in order] != list(range(len(lua_btns))):
        fail("btn's indices %s are not moy_lua.c's buttons %s" % (order, lua_btns))
    else:
        print("  ok   btn's indices are the Lua binding's button names, in order")

    header = read(LIBMOY, "include", "moy_wasm.h")
    snd = next(r for r in rows if r["name"] == "snd")["notes"]
    proposal = read(ROOT, "proposals", "wasm-runtime.md")
    for const, unit in (("MOY_WASM_SND_RATE", " Hz"), ("MOY_WASM_SND_DEPTH", " frames")):
        value = re.search(r"#define %s\s+(\d+)" % const, header).group(1)
        if value + unit not in snd or "{:,}".format(int(value)) + unit not in proposal:
            fail("snd: moy_wasm.h's %s is %s; the table's note and the proposal "
                 "must say %s%s" % (const, value, value, unit))
    print("  ok   snd's rate and depth are moy_wasm.h's in the table and the proposal")

    if FAILS:
        sys.exit("wasm table: %d failure%s" % (len(FAILS), "" if len(FAILS) == 1 else "s"))
    print("wasm table: the import table, the verb table and the C binding agree")


if __name__ == "__main__":
    main()
