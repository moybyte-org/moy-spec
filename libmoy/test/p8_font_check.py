#!/usr/bin/env python3
"""The PICO-8 font in libmoy/src/moy_p8.c is the one in p8_lua_port.py.

Two copies of 96 glyphs exist on purpose -- the C draws them for a host that
has the p8 machine, the Lua for a host that does not -- and the only thing
that keeps them one font is this check. Run by `make p8-test`.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def lua_hex(src, name):
    m = re.search(r'local %s = \{\}\n  do\n    local hex = "([0-9a-f]+)"\n((?:\s+\.\. "[0-9a-f]+"\n)+)' % name, src)
    if not m:
        sys.exit("%s: hex block not found in p8_lua_port.py" % name)
    return m.group(1) + "".join(re.findall(r'"([0-9a-f]+)"', m.group(2)))


def c_values(src, name):
    m = re.search(r"%s\[[^\]]*\] = \{(.*?)\};" % re.escape(name), src, re.S)
    if not m:
        sys.exit("%s: array not found in moy_p8.c" % name)
    return [int(v, 16) for v in re.findall(r"0x([0-9a-fA-F]+)", m.group(1))]


def main():
    with open(os.path.join(ROOT, "p8_lua_port.py"), encoding="utf-8") as f:
        lua = f.read()
    with open(os.path.join(ROOT, "libmoy", "src", "moy_p8.c"), encoding="utf-8") as f:
        c = f.read()
    g = lua_hex(lua, "P8_GLYPHS")
    want = [int(g[i:i + 4], 16) for i in range(0, len(g), 4)]
    got = c_values(c, "P8_GLYPHS")
    if want != got:
        sys.exit("P8_GLYPHS differ between the shim and moy_p8.c")
    w = lua_hex(lua, "P8_WIDE")
    want = [int(w[i:i + 2], 16) for i in range(0, len(w), 2)]
    got = c_values(c, "P8_WIDE")
    if want != got:
        sys.exit("P8_WIDE differ between the shim and moy_p8.c")
    print("p8 font: the C and the Lua carry the same %d glyphs" % (96 + 26))


if __name__ == "__main__":
    main()
