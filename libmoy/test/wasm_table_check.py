#!/usr/bin/env python3
"""The wasm import table is the verb table, and the C binding is the table.

    python3 test/wasm_table_check.py

wasm-imports.json is the import table of SPEC.md 16, the WebAssembly binding,
and four things must agree with it or the "one verb table, two bindings"
claim is prose:

  * its names are exactly the globals libmoy's Lua binding installs (parsed
    from src/moy_lua.c: the VERBS table and open_host_verbs, as the reference
    console's own deny-list test does) plus the binding's own;
  * src/moy_wasm.c's NativeSymbol array names the same rows, in the same
    order, at the same WAMR signature strings;
  * each row's WAMR string says what its wasm type says, and each row's SPEC
    section exists -- a row only this binding has names a section of 16;
  * include/moy_cart.h, the header a C cart includes, declares every row, in
    the table's order, imported from "moy" under the row's name, at the row's
    wasm type once its C types are lowered to wasm32's.

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
# the cart's own files, the receiver a Lua layer method has for free, the
# sample stream, the cart's own work across the cores, and its writable files.
WASM_ONLY = {"blit", "blit565", "read", "target", "snd", "par", "write", "erase", "list"}

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


# A C parameter or result type -> its wasm32 value type. A pointer is an
# offset into linear memory, so any pointer is an i32.
C_TYPES = {"int32_t": "i32", "float": "f32", "int64_t": "i64", "double": "f64"}


def c_type(decl):
    decl = decl.strip()
    if "*" in decl:
        return "i32"
    words = [w for w in decl.split() if w != "const"]
    return C_TYPES.get(words[0]) if words else None


def cart_declarations(src):
    """[(import name, C name, [param types], [result types])] from moy_cart.h,
    in file order; a type that is not a wasm32 value type is None."""
    body = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    out = []
    for m in re.finditer(r"MOY_IMPORT\((\w+)\)\s+([^;]*?)\bmoy_(\w+)\s*\(([^)]*)\)\s*;",
                         body):
        ret = m.group(2).strip()
        params = [] if m.group(4).strip() in ("", "void") else \
            [c_type(re.sub(r"\w+$", "", p.strip())) for p in m.group(4).split(",")]
        results = [] if ret == "void" else [c_type(ret)]
        out.append((m.group(1), m.group(3), params, results))
    return out


def check_cart_header(src, rows):
    decls = cart_declarations(src)
    if 'import_module("moy")' not in src or "import_name(#name)" not in src:
        fail('moy_cart.h\'s MOY_IMPORT does not import from "moy" under the row\'s name')
    for imp, cname, _, _ in decls:
        if imp != cname:
            fail("moy_cart.h imports %s as moy_%s" % (imp, cname))
    if [d[0] for d in decls] != [r["name"] for r in rows]:
        fail("moy_cart.h does not declare the table's rows in its order: only in the "
             "header %s, only in the table %s"
             % (sorted({d[0] for d in decls} - {r["name"] for r in rows}),
                sorted({r["name"] for r in rows} - {d[0] for d in decls})))
    by_name = dict((r["name"], r) for r in rows)
    for imp, _, params, results in decls:
        r = by_name.get(imp)
        if r and (params != r["params"] or results != r["results"]):
            fail("moy_cart.h: moy_%s lowers to (%s) -> (%s); the table says (%s) -> (%s)"
                 % (imp, ", ".join(map(str, params)), ", ".join(map(str, results)),
                    ", ".join(r["params"]), ", ".join(r["results"])))
    btn = next(r for r in rows if r["name"] == "btn")["notes"]
    order = [n.upper() for n, _ in re.findall(r"(\w+) (\d)", re.search(r"-- (.*?) --", btn).group(1))]
    enum = re.search(r"enum \{ (MOY_LEFT[^}]*) \}", src)
    if not enum or [e.strip()[4:] for e in enum.group(1).split(",")] != order:
        fail("moy_cart.h's button names are not btn's indices %s" % order)
    print("  ok   moy_cart.h declares the table's %d rows, in order, at their types"
          % len(decls))


def main():
    table = json.loads(read(ROOT, "wasm-imports.json"))
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
        spec = r["spec"].lstrip("§")
        if spec not in sections:
            fail("%s: SPEC.md has no section %s" % (r["name"], r["spec"]))
        if (r["name"] in WASM_ONLY) != spec.startswith("16."):
            fail("%s: its section is %s; a row is in 16 exactly when only this "
                 "binding has it" % (r["name"], r["spec"]))
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
    spec_md = read(ROOT, "SPEC.md")
    cart_h = read(LIBMOY, "include", "moy_cart.h")
    for const, unit in (("MOY_WASM_SND_RATE", " Hz"), ("MOY_WASM_SND_DEPTH", " frames")):
        value = re.search(r"#define %s\s+(\d+)" % const, header).group(1)
        if (value + unit not in snd or "{:,}".format(int(value)) + unit not in spec_md
                or value + unit not in " ".join(cart_h.split())):
            fail("snd: moy_wasm.h's %s is %s; the table's note, SPEC.md 16.9 and "
                 "moy_cart.h must say %s%s" % (const, value, value, unit))
    print("  ok   snd's rate and depth are moy_wasm.h's in the table, SPEC.md and moy_cart.h")

    check_cart_header(cart_h, rows)

    if FAILS:
        sys.exit("wasm table: %d failure%s" % (len(FAILS), "" if len(FAILS) == 1 else "s"))
    print("wasm table: the import table, the verb table and the C binding agree")


if __name__ == "__main__":
    main()
