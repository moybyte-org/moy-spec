#!/usr/bin/env python3
"""`moy check` on runtime "wasm" carts (SPEC.md 16).

The fixtures under test/wasm/ are WAT source; each is assembled into a cart in
a scratch directory and handed to the real CLI, so what is tested is the
command an author runs. hello.moy must pass with no warning -- the binding is
the spec's, so a well-formed compiled cart draws none -- and every other
fixture must be refused with the finding its name promises. The cases below the fixtures reach
the module checker directly, for the refusals that are one line of WAT each.
Run by `make wasm-check`.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FIXTURES = os.path.join(HERE, "wasm")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import wat                                   # noqa: E402
from moycore import wasm as mw               # noqa: E402
from moycore import check as mc              # noqa: E402

# fixture -> the finding code it must be refused with; None passes.
EXPECT = {
    "hello": None,
    "foreign_import": "wasm.import",
    "memory_mismatch": "wasm.memory",
    "missing_export": "wasm.export",
    "bad_signature": "wasm.import",
    "start_function": "wasm.start",
}

FAILS = []


def fail(msg):
    FAILS.append(msg)
    print("  FAIL " + msg)


def run_check(cart):
    p = subprocess.run([sys.executable, os.path.join(ROOT, "moy.py"), "check", cart],
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def fixtures(scratch):
    found = sorted(d[:-4] for d in os.listdir(FIXTURES) if d.endswith(".moy"))
    if found != sorted(EXPECT):
        fail("fixtures on disk %s, expectations for %s" % (found, sorted(EXPECT)))
    for name in found:
        cart = os.path.join(scratch, name + ".moy")
        wat.build_cart(os.path.join(FIXTURES, name + ".moy"), cart)
        rc, out = run_check(cart)
        want = EXPECT.get(name)
        errors = [ln for ln in out.splitlines() if ln.strip().startswith("error")]
        warnings = [ln for ln in out.splitlines() if ln.strip().startswith("warn")]
        if want is None:
            if rc != 0 or errors or warnings or not out.rstrip().endswith("OK."):
                fail("%s should pass with no warning, got rc=%d:\n%s" % (name, rc, out))
            elif "imports 19 of the table's" not in out:
                fail("%s: the import count is not reported:\n%s" % (name, out))
            else:
                print("  ok   %s passes" % name)
        else:
            codes = [ln.split()[1].rstrip(":") for ln in errors]
            if rc == 0 or want not in codes:
                fail("%s should be refused with %s, got rc=%d:\n%s"
                     % (name, want, rc, out))
            else:
                print("  ok   %s refused (%s)" % (name, want))


BASE = """
  (import "moy" "cls" (func $cls (param i32)))
  %s
  (func (export "_init"))
  (func (export "_update") (param f32))
  (func (export "_draw"))
"""


def module(memory, extra=""):
    return wat.assemble("(module %s)" % (BASE % memory + extra))


def codes(blob, manifest):
    return [c for lvl, c, _ in mw.check_module(blob, manifest, []) if lvl == "error"]


def cases():
    ok_mem = '(memory (export "memory") 2 2)'
    m2 = {"memory": 2}

    def expect(label, got, want):
        if (want is None and got) or (want is not None and want not in got):
            fail("%s: want %s, got %s" % (label, want or "no error", got))
        else:
            print("  ok   %s" % label)

    expect("the base module passes", codes(module(ok_mem), m2), None)
    expect("a memory with no maximum",
           codes(module('(memory (export "memory") 2)'), m2), "wasm.memory")
    expect("a memory whose minimum is not its maximum",
           codes(module('(memory (export "memory") 2 4)'), m2), "wasm.memory")
    expect("a manifest with no memory", codes(module(ok_mem), {}),
           "manifest.memory")
    expect("a manifest memory that is not a whole count",
           codes(module(ok_mem), {"memory": "2"}), "manifest.memory")
    expect("an imported memory",
           codes(wat.assemble('(module (import "moy" "memory" (memory 2 2))'
                              '(func (export "_init")) (func (export "_update")'
                              ' (param f32)) (func (export "_draw")))'), m2),
           "wasm.memory")
    expect("a name outside the table",
           codes(module(ok_mem, '(import "moy" "poke" (func (param i32 i32)))'),
                 m2), "wasm.import")
    expect("a global import from moy",
           codes(module(ok_mem, '(import "moy" "W" (global i32))'), m2),
           "wasm.import")
    expect("snd at its type",
           codes(module(ok_mem, '(import "moy" "snd" (func (param i32 i32) '
                                '(result i32)))'), m2), None)
    expect("snd at another type",
           codes(module(ok_mem, '(import "moy" "snd" (func (param i32 i32)))'),
                 m2), "wasm.import")
    par = '(import "moy" "par" (func (param i32 i32 i32 i32)))'
    item = '(func (export "_par") (param i32 i32))'
    sp = '(global (export "__stack_pointer") (mut i32) (i32.const 1024))'
    expect("par with its item and its stack pointer",
           codes(module(ok_mem, par + item + sp), m2), None)
    expect("par with no _par export",
           codes(module(ok_mem, par + sp), m2), "wasm.export")
    expect("par with no __stack_pointer export",
           codes(module(ok_mem, par + item), m2), "wasm.export")
    expect("a _par at another type, par or not",
           codes(module(ok_mem, '(func (export "_par") (param i32))'), m2),
           "wasm.export")
    expect("a __stack_pointer that cannot be set",
           codes(module(ok_mem, par + item
                         + '(global (export "__stack_pointer") i32 (i32.const 1024))'),
                 m2), "wasm.export")
    expect("par at another type",
           codes(module(ok_mem, '(import "moy" "par" (func (param i32 i32 i32)))'
                         + item + sp), m2), "wasm.import")
    expect("_update at the wrong type",
           codes(wat.assemble('(module (memory (export "memory") 2 2)'
                              '(func (export "_init")) (func (export "_update"))'
                              '(func (export "_draw")))'), m2), "wasm.export")
    expect("no memory export",
           codes(wat.assemble('(module (memory 2 2) (func (export "_init"))'
                              '(func (export "_update") (param f32))'
                              '(func (export "_draw")))'), m2), "wasm.export")
    expect("bytes that are not a module", codes(b"\x00asn\x01\x00\x00\x00", m2),
           "wasm.module")
    expect("a truncated module", codes(module(ok_mem)[:40], m2), "wasm.module")

    floor = mw.MEMORY_FLOOR_PAGES
    try:
        mw.MEMORY_FLOOR_PAGES = 1
        found = mw.check_module(module(ok_mem), m2, [])
        warned = [m for lvl, c, m in found
                  if lvl == "warn" and c == "manifest.memory"]
        refused = [c for lvl, c, _ in found if lvl == "error"]
        if refused or not warned or "floor of 1" not in warned[0] \
                or "runs only on consoles with more memory" not in warned[0]:
            fail("a declared memory above the floor: want a warning naming the "
                 "floor and no error, got %s" % (found,))
        else:
            print("  ok   a declared memory above the floor is a warning")
        mw.MEMORY_FLOOR_PAGES = 2
        expect("a declared memory at the floor", codes(module(ok_mem), m2), None)
    finally:
        mw.MEMORY_FLOOR_PAGES = floor

    manifest = {"format": "moy-1", "title": "t", "runtime": "wasm", "memory": 2}
    files = {"main.wasm": module(ok_mem)}

    def cart_codes(extra):
        m = dict(manifest)
        m.update(extra)
        f = dict(files)
        f["manifest.json"] = json.dumps(m).encode()
        return [c for lvl, c, _ in mc.check_wasm_files(f) if lvl == "error"]

    expect("a whole cart with main defaulted to main.wasm", cart_codes({}), None)
    expect("a wasm cart listing sources", cart_codes({"sources": ["main.wasm"]}),
           "manifest.sources")
    expect("a canvas outside the set", cart_codes({"canvas": "100x100"}),
           "manifest.canvas")
    expect("a main that is not in the cart", cart_codes({"main": "game.wasm"}),
           "manifest.main")


def the_table_is_readable():
    table = mw.load_table()
    for name in ("blit", "blit565", "read", "target", "snd", "par", "cls"):
        if name not in table:
            fail("the import table has no %s" % name)
    print("  ok   the import table loads (%d rows)" % len(table))


def main():
    scratch = tempfile.mkdtemp(prefix="moy-wasm-check-")
    try:
        print("wasm check: the fixtures, through moy check")
        fixtures(scratch)
        print("wasm check: the module checker, one rule at a time")
        cases()
        the_table_is_readable()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    if FAILS:
        sys.exit("wasm check: %d failure%s" % (len(FAILS), "" if len(FAILS) == 1 else "s"))
    print("wasm check: every fixture and rule behaves")


if __name__ == "__main__":
    main()
