#!/usr/bin/env python3
"""The porter's statement transforms, on the VM that runs their output.

    python3 libmoy/test/p8_port_check.py        (`make -C libmoy p8-test`)

The cart corpus cannot check a transform that no corpus cart happens to
contain, and it cannot check the cases a transform must REFUSE at all -- a
fold that fires one statement too wide leaves a cart that still runs and
draws the wrong thing. So the shapes are asserted here, on the converted text,
where a near miss is visible.

Two of them: `fold_lut_span` (`for a=i,j do poke(a,peek(lut|peek(a))) end` ->
`__p8_lut_span(i, j, lut)`, the span dank tomb lights its screen with), and
the NATIVE BIT OPERATORS -- `a|b` -> `__p8_bor(a, b)`, one call rather than a
floor around each operand. That rewrite has to know Lua's precedence, which a
wrapper around a primary does not, and it has to know which operands are
integers ALREADY, which is a claim about the shim's verbs; both are asserted
here, in each direction.
"""
import os
import re
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


def emits(name, src, want):
    """The converted line, exactly."""
    got = convert(src).strip()
    if got != want:
        FAIL.append("%s: wanted %r, got %r" % (name, want, got))


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

    bitops()
    shifts_by_16()

    # Same rule for the nine: every name the operator rewrite can emit is a
    # name the shim BINDS. It binds them to the nine verbs -- one lane, so
    # `x >> 1` and `shr(x, 1)` cannot answer differently -- and the second
    # implementation that used to sit here (`function __p8_shr(a, b) return
    # flr(a) >> flr(b) end`) is gone; a returning `function __p8_` is that
    # divergence coming back.
    ops = sorted(set(p8_lua_port._BIT_VERB.values()) | {p8_lua_port._BNOT_VERB})
    for verb in ops:
        if not re.search(r"(?m)(^|[\s,])%s\s*[,=][^=]" % re.escape(verb),
                         p8_lua_port.SHIM):
            FAIL.append("the shim does not bind %s" % verb)
    if "function __p8_b" in p8_lua_port.SHIM or "function __p8_s" in p8_lua_port.SHIM:
        FAIL.append("the shim defines a second bit-operator lane again")

    for line in FAIL:
        print("p8 port: " + line)
    if FAIL:
        return 1
    print("p8 port: the lut-span fold takes its shape and nothing else, and "
          "the bit operators are one call each with no floor to spare")
    return 0


def bitops():
    """`a | b` -> `__p8_bor(a, b)`, and the operand that needs nothing."""
    # ONE CALL PER OPERATOR, all nine of p8's -- including the two rotates,
    # which have no Lua operator to fall back to.
    emits("or", "x=a|b", "x=__p8_bor(a, b)")
    emits("and", "x=a&b", "x=__p8_band(a, b)")
    emits("xor", "x=a^^b", "x=__p8_bxor(a, b)")
    emits("not", "x=~a", "x=__p8_bnot(a)")
    emits("shift left", "x=a<<b", "x=__p8_shl(a, b)")
    emits("shift right", "x=a>>b", "x=__p8_shr(a, b)")
    emits("logical shift right", "x=a>>>b", "x=__p8_lshr(a, b)")
    emits("rotate left", "x=a<<>b", "x=__p8_rotl(a, b)")
    emits("rotate right", "x=a>><b", "x=__p8_rotr(a, b)")
    # A rotate is a call even when both operands are integers, because there
    # is nothing to leave behind.
    emits("a rotate of two integers", "x=peek(a)<<>2", "x=__p8_rotl(peek(a), 2)")
    # `~=` is one token and not a bit operator at all.
    emits("not-equal is not xor", "x=a~=b", "x=a~=b")

    # PRECEDENCE. A call takes the WHOLE operand, which wrapping the primary
    # never had to: every one of these was a different expression before.
    emits("the right operand's arithmetic", "x=a&b+1", "x=__p8_band(a, b+1)")
    emits("the left operand's arithmetic", "x=a+1&b", "x=__p8_band(a+1, b)")
    emits("a comparison is looser", "x=a&b==c", "x=__p8_band(a, b)==c")
    emits("a comparison on the left", "x=a==b&c", "x=a==__p8_band(b, c)")
    emits("and binds looser still", "x=a and b&c", "x=a and __p8_band(b, c)")
    emits("`&` binds tighter than `|`", "x=a|b&c",
          "x=__p8_bor(a, __p8_band(b, c))")
    emits("`&` on the left of `|`", "x=a&b|c",
          "x=__p8_bor(__p8_band(a, b), c)")
    emits("a shift binds tighter than `&`", "x=a&b>>c",
          "x=__p8_band(a, __p8_shr(b, c))")
    emits("left to right", "x=a|b|c", "x=__p8_bor(__p8_bor(a, b), c)")
    emits("concatenation binds tighter", "x=a..b&c", "x=__p8_band(a..b, c)")
    emits("a unary minus comes along", "x=-a|b", "x=__p8_bor(-a, b)")
    emits("`#` is the operand, not the table", "x=#t&a",
          "x=__p8_band(#t, a)")
    # p8 breaks a line at the operator, and dank tomb's lighting is one of
    # them: the operand on the next line is still the operand.
    emits("split at the operator", "x=a|\nb", "x=__p8_bor(a, b)")
    if convert("x=a|\nb") != "\nx=__p8_bor(a, b)\n":
        FAIL.append("joining a split operator moved the cart's line numbers")
    # A compound assignment writes an operator of its own, and it gets the
    # same treatment -- `x = x & (y)` refused a fractional x before.
    emits("a compound assignment", "x&=y", "x = __p8_band(x, (y))")

    # NO WRAPPER AT ALL where both operands are already integers: the bare Lua
    # instruction, no call of any kind. Only `&`, `|` and `^^` are on this
    # list, and the reason is p8's 16.16 image: those three cannot move a bit
    # across the point or off the end of it, so two integers meeting in one of
    # them answer the same in either arithmetic. Every other operator can --
    # see the list below.
    for src in ("x=peek(a)&0xf0", "x=peek(a)|peek(b)", "x=peek2(a)&0xff",
                "x=mget(i,j)&7", "x=fget(n)&2", "x=flr(a)&flr(b)",
                "x=ceil(a)|1", "x=#t&3", "x=1|2", "x=peek(a)&0xffff",
                "x=peek(a)&-1", "x=(peek(a)&0xf)|(peek(b)&0xf0)",
                "x=peek(a)^^peek(b)"):
        got = convert(src).strip()
        if "__p8_" in got or got.count("flr(") != src.count("flr("):
            FAIL.append("an integer operand still got a wrapper: %r -> %r"
                        % (src, got))

    # AND A CALL where it cannot be proved. Each of these was a `yes` that
    # would have cost a cart "number has no integer representation".
    for name, src in (
            ("fget with a bit is a BOOLEAN", "x=fget(n,3)&2"),
            ("peek4 reads a 16.16 word", "x=peek4(a)&1"),
            ("band() can answer a fraction", "x=band(a,b)|1"),
            ("shr() can answer a fraction", "x=shr(a,b)|1"),
            ("a fractional literal", "x=a&0x0.0001"),
            ("a decimal literal", "x=a&1.5"),
            ("arithmetic on an integer is not one", "x=peek(a)+1&3"),
            ("a field is not the verb", "x=t.peek(a)|1"),
            ("a method is not the verb", "x=t:peek(a)|1"),
            ("a bare name", "x=v&1"),
            # Two integers are not enough for these five: p8 runs them on the
            # 16.16 image, where `peek(a)>>4` keeps the four bits it shifted
            # past the point (`3>>1` is 1.5), `~peek(a)` sets all sixteen of
            # them, and `1<<15` lands on -32768 rather than 32768. Lua's
            # integer operator cannot say any of that, so there is nothing to
            # leave behind and the call stands.
            ("a right shift keeps its fraction", "x=peek(a)>>4"),
            ("a logical shift keeps its fraction", "x=peek(a)>>>4"),
            ("a complement sets the fraction", "x=~peek(a)"),
            ("a left shift can run off the top", "x=1<<peek(a)"),
            ("and a shift inside a chain takes the chain with it",
             "x=peek(a)|peek(b)>>2")):
        if "__p8_" not in convert(src):
            FAIL.append("%s: took an operand on trust -- %r"
                        % (name, convert(src).strip()))

    # THE CART'S OWN. A verb the cart defines, declares, assigns, loops over
    # or takes as a parameter is not the shim's, and the rule is off for that
    # name.
    for name, src in (
            ("defined", "function peek(z) return z end\nx=peek(a)|1"),
            ("declared local", "local peek=0\nx=peek(a)|1"),
            ("assigned", "peek=myread\nx=peek(a)|1"),
            ("a for variable", "for mget=1,3 do end\nx=mget(i,j)|1"),
            ("a parameter", "function f(peek) return peek(1)|2 end")):
        if "__p8_" not in convert(src):
            FAIL.append("a shadowed verb kept its promise (%s) -- %r"
                        % (name, convert(src).strip()))
    # ...and a name that merely LOOKS like one still counts as the shim's.
    if "__p8_" in convert("peeker=1\nx=peek(a)|1"):
        FAIL.append("a longer name shadowed the verb it starts with")


def shifts_by_16():
    """The 16.16 refusal, read off the text the rewrite now emits.

    A cart that unpacks its data with fixed-point shifts cannot run here: the
    port's numbers are Lua's, and `12345 >>> 16` answers 0 where PICO-8 answers
    0.18836. `classify` refuses such a cart BEFORE anything is written, and the
    rule reads the CONVERTED body -- so when the operator rewrite replaced every
    `>>` with a `__p8_lshr(...)` call the refusal stopped firing on celeste 2,
    the cart it was written for, whose count is `16-cache_bits` and never the
    literal 16. It classified as "runs" and drew empty rooms.
    """
    px9 = ("function getval(bits)\n"
           " if cache_bits<16 then\n"
           "  cache+=%src>>>16-cache_bits\n"
           "  cache_bits+=16\n"
           "  src+=2\n"
           " end\n"
           " local val=cache<<32-bits>>>16-bits\n"
           " cache=cache>>>bits\n"
           " return val\n"
           "end")
    v = p8_lua_port.classify_body(convert(px9))
    if v["verdict"] != "refused":
        FAIL.append("px9's bit cache classified %r, not refused -- %r"
                    % (v["verdict"], convert(px9).strip()))

    # ...and a count that merely CONTAINS a sixteen is not a shift by one:
    # dank tomb's `shl(1, lw(0x70,x,y)/16)` shifts by a sixteenth of a word.
    for name, src, want in (
            ("a literal count", "x=shl(a,16)", True),
            ("the count minus an offset", "x=lshr(peek2(s),16-n)", True),
            ("the count plus an offset", "x=shr(a,n+16)", True),
            ("a sixteenth of something", "x=shl(1,lw(0x70,i,j)/16)", False),
            ("a bigger literal", "x=shl(a,160)", False),
            ("sixteen times something", "x=shl(a,16*n)", False)):
        got = p8_lua_port._shifts_by_16(
            p8_lua_port._strip_lua(convert(src)))
        if got != want:
            FAIL.append("%s: shifts-by-16 said %s -- %r"
                        % (name, got, convert(src).strip()))


if __name__ == "__main__":
    sys.exit(main())
