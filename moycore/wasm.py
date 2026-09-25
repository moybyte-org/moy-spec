"""A compiled cart's module, read and checked (proposals/wasm-runtime.md).

A cart whose manifest says `"runtime": "wasm"` carries a WebAssembly module as
its `main`, and everything the proposal pins about that module is decidable
from its bytes: which imports it declares, which exports, what memory. This
reads exactly those sections and checks them against the import table
(proposals/wasm-imports.json) and the manifest. It does not validate code --
a host's loader does that -- and it never runs anything.

Tracks the proposal, which is not part of core 0.3.

Stdlib only and MicroPython-importable, like the rest of moycore.
"""

import json

from . import _data

PAGE = 65536
IMPORT_MODULE = "moy"
TABLE_FILE = "proposals/wasm-imports.json"

# The tier's memory floor in pages: the reference implementation's floor
# board's share of its cart-runtime reserve, measured with the runtime
# resident (the proposal's Memory section and open item 8). None until that
# measurement lands; while it is None no declared size is refused for size.
MEMORY_FLOOR_PAGES = None

# name -> (params, results), the proposal's required exports.
EXPORTS = {
    "_init": ((), ()),
    "_update": (("f32",), ()),
    "_draw": ((), ()),
}

VALTYPES = {0x7F: "i32", 0x7E: "i64", 0x7D: "f32", 0x7C: "f64",
            0x7B: "v128", 0x70: "funcref", 0x6F: "externref"}
KINDS = ("func", "table", "memory", "global")

# Section ids the wasm32 MVP profile has. 12 (data count) and 13 (tags) belong
# to later proposals.
MVP_SECTIONS = tuple(range(0, 12))


class ModuleError(Exception):
    """The bytes are not a module this checker can read."""


class _Reader(object):
    def __init__(self, blob, pos=0, end=None):
        self.b = blob
        self.pos = pos
        self.end = len(blob) if end is None else end

    def byte(self):
        if self.pos >= self.end:
            raise ModuleError("truncated at byte %d" % self.pos)
        v = self.b[self.pos]
        self.pos += 1
        return v

    def uleb(self):
        result, shift = 0, 0
        while True:
            b = self.byte()
            result |= (b & 0x7F) << shift
            shift += 7
            if not b & 0x80:
                return result
            if shift > 35:
                raise ModuleError("malformed integer at byte %d" % self.pos)

    def bytes(self, n):
        if self.pos + n > self.end:
            raise ModuleError("truncated at byte %d" % self.pos)
        v = self.b[self.pos:self.pos + n]
        self.pos += n
        return v

    def name(self):
        raw = self.bytes(self.uleb())
        try:
            return bytes(raw).decode("utf-8")
        except UnicodeError:
            raise ModuleError("a name that is not UTF-8")

    def valtype(self):
        t = self.byte()
        if t not in VALTYPES:
            raise ModuleError("unknown value type 0x%02x" % t)
        return VALTYPES[t]

    def limits(self):
        flags = self.byte()
        lo = self.uleb()
        hi = self.uleb() if flags & 1 else None
        return flags, lo, hi


def parse(blob):
    """The parts of a module the proposal constrains, as a dict:

      types    [(params, results)]
      imports  [(module, name, kind, desc)] -- desc is a type index for a
               function, (flags, min, max) for a memory, None otherwise
      funcs    [type index] for the module's own functions
      memories [(flags, min, max)] for the module's own memories
      exports  [(name, kind, index)]
      start    a function index, or None
      sections [section id, in order]

    Raises ModuleError when the bytes are not a readable module."""
    if bytes(blob[:4]) != b"\x00asm":
        raise ModuleError("not a WebAssembly module (no \\0asm header)")
    if bytes(blob[4:8]) != b"\x01\x00\x00\x00":
        raise ModuleError("not WebAssembly version 1")
    out = {"types": [], "imports": [], "funcs": [], "memories": [],
           "exports": [], "start": None, "sections": []}
    r = _Reader(blob, 8)
    while r.pos < r.end:
        sid = r.byte()
        size = r.uleb()
        body = _Reader(blob, r.pos, r.pos + size)
        if body.end > r.end:
            raise ModuleError("section %d runs past the end of the module" % sid)
        r.pos = body.end
        out["sections"].append(sid)
        if sid == 1:
            for _ in range(body.uleb()):
                if body.byte() != 0x60:
                    raise ModuleError("a type that is not a function type")
                params = tuple(body.valtype() for _ in range(body.uleb()))
                results = tuple(body.valtype() for _ in range(body.uleb()))
                out["types"].append((params, results))
        elif sid == 2:
            for _ in range(body.uleb()):
                mod, name = body.name(), body.name()
                k = body.byte()
                if k == 0:
                    desc = body.uleb()
                elif k == 1:
                    body.byte()
                    body.limits()
                    desc = None
                elif k == 2:
                    desc = body.limits()
                elif k == 3:
                    body.valtype()
                    body.byte()
                    desc = None
                else:
                    raise ModuleError("unknown import kind %d" % k)
                out["imports"].append((mod, name, KINDS[k], desc))
        elif sid == 3:
            out["funcs"] = [body.uleb() for _ in range(body.uleb())]
        elif sid == 5:
            out["memories"] = [body.limits() for _ in range(body.uleb())]
        elif sid == 7:
            for _ in range(body.uleb()):
                name = body.name()
                k = body.byte()
                if k > 3:
                    raise ModuleError("unknown export kind %d" % k)
                out["exports"].append((name, KINDS[k], body.uleb()))
        elif sid == 8:
            out["start"] = body.uleb()
    return out


def func_type(mod, index):
    """(params, results) of function `index` in the module's index space --
    imported functions first, as wasm numbers them."""
    imported = [d for _, _, k, d in mod["imports"] if k == "func"]
    if index < len(imported):
        t = imported[index]
    elif index - len(imported) < len(mod["funcs"]):
        t = mod["funcs"][index - len(imported)]
    else:
        return None
    return mod["types"][t] if t < len(mod["types"]) else None


def load_table():
    """{name: (params, results)} from the proposal's import table."""
    rows = json.loads(_data.read(TABLE_FILE))["imports"]
    return dict((r["name"], (tuple(r["params"]), tuple(r["results"])))
                for r in rows)


def _sig(t):
    return "(%s) -> (%s)" % (", ".join(t[0]), ", ".join(t[1]))


def check_module(blob, manifest, findings, table=None):
    """Every rule of the proposal's module shape, against `blob` and the
    manifest's declared memory. Appends (level, code, message) findings."""
    table = load_table() if table is None else table
    try:
        mod = parse(blob)
    except ModuleError as exc:
        findings.append(("error", "wasm.module", str(exc)))
        return findings

    later = [s for s in mod["sections"] if s not in MVP_SECTIONS]
    if later:
        findings.append(("error", "wasm.profile",
                         "section %d is past the wasm32 MVP profile the "
                         "proposal pins" % later[0]))

    for m, name, kind, desc in mod["imports"]:
        where = "%s.%s" % (m, name)
        if m != IMPORT_MODULE:
            findings.append(("error", "wasm.import",
                             'imports %s; a compiled cart imports only from '
                             'module "%s"' % (where, IMPORT_MODULE)))
        elif kind != "func":
            findings.append(("error", "wasm.import",
                             "imports %s as a %s; the table holds only "
                             "functions" % (where, kind)))
        elif name not in table:
            findings.append(("error", "wasm.import",
                             "imports %s, which is not in the import table "
                             "(%s)" % (where, TABLE_FILE)))
        else:
            got = mod["types"][desc] if desc < len(mod["types"]) else None
            if got != table[name]:
                findings.append(("error", "wasm.import",
                                 "imports %s as %s; the table says %s"
                                 % (where, _sig(got) if got else "?",
                                    _sig(table[name]))))

    exports = dict((n, (k, i)) for n, k, i in mod["exports"])
    for name in sorted(EXPORTS):
        want = EXPORTS[name]
        if name not in exports or exports[name][0] != "func":
            findings.append(("error", "wasm.export",
                             "no %s export; the host calls %s%s"
                             % (name, name, _sig(want))))
            continue
        got = func_type(mod, exports[name][1])
        if got != want:
            findings.append(("error", "wasm.export",
                             "%s is %s; the proposal says %s"
                             % (name, _sig(got) if got else "?", _sig(want))))
    if "memory" not in exports or exports["memory"][0] != "memory":
        findings.append(("error", "wasm.export",
                         "no memory export; the module's linear memory is "
                         "exported as \"memory\""))

    if mod["start"] is not None:
        findings.append(("error", "wasm.start",
                         "the module has a start function; nothing may run "
                         "before _init"))

    check_memory(mod, manifest, findings)

    used = [n for m, n, k, _ in mod["imports"] if m == IMPORT_MODULE and n in table]
    findings.append(("info", "wasm.imports",
                     "imports %d of the table's %d functions"
                     % (len(used), len(table))))
    return findings


def check_memory(mod, manifest, findings):
    declared = manifest.get("memory")
    if isinstance(declared, bool) or not isinstance(declared, int) \
            or declared < 1:
        findings.append(("error", "manifest.memory",
                         "a wasm cart declares its linear memory as \"memory\": "
                         "a positive whole number of 64 KiB pages (got %r)"
                         % (declared,)))
        declared = None
    elif MEMORY_FLOOR_PAGES is not None and declared > MEMORY_FLOOR_PAGES:
        findings.append(("error", "manifest.memory",
                         "declares %d pages; the compiled tier's floor is %d, so "
                         "this is a demo, not a cart" % (declared, MEMORY_FLOOR_PAGES)))

    imported = [d for _, _, k, d in mod["imports"] if k == "memory"]
    own = mod["memories"]
    if imported:
        findings.append(("error", "wasm.memory",
                         "the module imports its memory; a cart's memory is its own"))
    if len(own) != 1:
        findings.append(("error", "wasm.memory",
                         "the module defines %d memories; it defines exactly one"
                         % len(own)))
        return
    flags, lo, hi = own[0]
    if flags & ~1:
        findings.append(("error", "wasm.memory",
                         "the memory is shared or 64-bit; the profile is wasm32 MVP"))
    if hi is None:
        findings.append(("error", "wasm.memory",
                         "the memory has no maximum; it is one fixed block, "
                         "minimum = maximum = the manifest's memory"))
    elif lo != hi:
        findings.append(("error", "wasm.memory",
                         "the memory runs from %d to %d pages; minimum and "
                         "maximum must be equal" % (lo, hi)))
    if declared is not None and (lo != declared or (hi is not None and hi != declared)):
        findings.append(("error", "wasm.memory",
                         "the module's memory is %d..%s pages but the manifest "
                         "declares %d" % (lo, "?" if hi is None else hi, declared)))
