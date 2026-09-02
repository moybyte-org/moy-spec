#!/usr/bin/env python3
"""The porter's statement transforms, on the VM that runs their output.

    python3 libmoy/test/p8_port_check.py        (`make -C libmoy p8-test`)

The cart corpus cannot check a transform that no corpus cart happens to
contain, and it cannot check the cases a transform must REFUSE at all -- a
fold that fires one statement too wide leaves a cart that still runs and
draws the wrong thing. So the shapes are asserted here, on the converted text,
where a near miss is visible.

Today that is `fold_lut_span`: `for a=i,j do poke(a,peek(lut|peek(a))) end` ->
`__p8_lut_span(i, j, lut)`, the span dank tomb lights its screen with.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

import p8_lua_port                                            # noqa: E402

FAIL = []


def convert(src):
    return p8_lua_port.p8_lua_to_lua54(src.split("\n"))


def folds(name, src, want="__p8_lut_span(gi,gb,bs)"):
    got = convert(src)
    if want not in got:
        FAIL.append("%s: wanted %s, got %r" % (name, want, got.strip()))


def keeps(name, src):
    if "__p8_lut_span" in convert(src):
        FAIL.append("%s: folded a statement it must not touch -- %r"
                    % (name, convert(src).strip()))


def main():
    # THE SHAPE, as dank tomb writes it: two lines, p8 memory sigils, and the
    # `flr(...)` the porter itself puts around a native bitop's operands.
    folds("the cart's own spelling",
          "for ls=gi,gb do\npoke(ls,@(bs|@ls))end")
    folds("one line", "for ls=gi,gb do poke(ls,@(bs|@ls)) end")
    # The same statement written out, with and without the wrappers the
    # porter would have added, and with spaces anywhere they are legal.
    folds("no flr", "for ls=gi,gb do poke(ls,peek(bs|peek(ls))) end")
    folds("parenthesised operands",
          "for ls=gi,gb do poke(ls,peek((bs)|(peek(ls)))) end")
    folds("spaced out",
          "for  ls = gi , gb  do  poke ( ls , peek ( ( flr ( bs ) | "
          "flr ( peek ( ls ) ) ) ) )  end")
    folds("split three ways",
          "for ls=gi,\ngb do\npoke(ls,peek(flr(bs)|flr(peek(ls))))\nend")
    # The bounds and the table may be any expression that cannot change
    # inside the loop.
    folds("expressions for the bounds",
          "for ls=mr+1,mr+63 do poke(ls,peek(t.lut[2]|peek(ls))) end",
          "__p8_lut_span(mr+1,mr+63,t.lut[2])")

    # THE LOOP VARIABLE, in each of its three places. A different name in any
    # one of them is a different statement.
    keeps("poked address is not the loop variable",
          "for ls=gi,gb do poke(lx,peek(bs|peek(ls))) end")
    keeps("peeked address is not the loop variable",
          "for ls=gi,gb do poke(ls,peek(bs|peek(lx))) end")
    keeps("the table is the loop variable",
          "for ls=gi,gb do poke(ls,peek(ls|peek(ls))) end")

    # A CALL in a hoisted argument: it would run once instead of every
    # iteration, so the fold may not take it.
    keeps("a call in the first bound",
          "for ls=f(1),gb do poke(ls,peek(bs|peek(ls))) end")
    keeps("a call in the second bound",
          "for ls=gi,f(1) do poke(ls,peek(bs|peek(ls))) end")
    keeps("a call in the table",
          "for ls=gi,gb do poke(ls,peek(lut(1)|peek(ls))) end")
    keeps("a method call in the table",
          "for ls=gi,gb do poke(ls,peek(t:lut()|peek(ls))) end")

    # Everything else about the shape.
    keeps("a step", "for ls=gi,gb,2 do poke(ls,peek(bs|peek(ls))) end")
    keeps("a second statement in the body",
          "for ls=gi,gb do poke(ls,peek(bs|peek(ls))) x=1 end")
    keeps("a generic for", "for ls in all(t) do poke(ls,peek(bs|peek(ls))) end")
    keeps("no peek on the inside",
          "for ls=gi,gb do poke(ls,peek(bs|ls)) end")
    keeps("two table lookups",
          "for ls=gi,gb do poke(ls,peek(bs|peek(peek(ls)))) end")
    keeps("a poke of two bytes",
          "for ls=gi,gb do poke(ls,peek(bs|peek(ls)),3) end")
    keeps("a comment inside it",
          "for ls=gi,gb do poke(ls,peek(bs|peek(ls))) --[[x]] end")

    # The LINE COUNT is what an error message points at, so the fold puts back
    # every newline it swallowed.
    src = "a=1\nfor ls=gi,gb do\npoke(ls,@(bs|@ls))end\nb=2"
    got = convert(src)
    if got.count("\n") != src.count("\n") + 1:
        FAIL.append("the fold moved the lines under the cart: %r" % got)

    # The name the fold emits has to be one the shim defines, or a cart that
    # matched calls nothing.
    if "function __p8_lut_span(" not in p8_lua_port.SHIM:
        FAIL.append("the shim does not define __p8_lut_span")

    for line in FAIL:
        print("p8 port: " + line)
    if FAIL:
        return 1
    print("p8 port: the lut-span fold takes its shape and nothing else")
    return 0


if __name__ == "__main__":
    sys.exit(main())
