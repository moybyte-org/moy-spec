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
    dialect()
    mouse()
    shifts_by_16()
    bit_twins()

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


def mouse():
    """p8's mouse, over the console's own pointer.

    The SHIM half is asserted here (the shape the porter emits); the two lanes
    it runs over -- libmoy's touch() and the snapshot behind it -- are the
    host's, and moybyte's tests/test_host_lua_binding.py pins those.
    """
    shim = p8_lua_port.SHIM
    # The latch runs once a TICK, beside the button latch, so three stat()
    # reads in one frame cannot disagree.
    if "p8_mouse_tick()" not in shim:
        FAIL.append("the shim never latches the mouse")
    # Gated on p8's OWN enable bit: a cart that never asks for a pointer must
    # not pay a crossing for one.
    if "0x5f2d" not in _lua_body(shim, "p8_mouse_tick").replace("L_", ""):
        FAIL.append("the mouse latch does not read p8's enable bit (0x5f2d)")
    # Captured as an UPVALUE, not read off _G every tick: a cart may take the
    # name `touch` for itself, which is exactly how `camera` crashed deep dark.
    if "local m_touch = touch" not in shim:
        FAIL.append("the shim reads touch() off _G instead of capturing it")
    for n in (32, 33, 34):
        if "if n == %d then return p8_m" % n not in shim:
            FAIL.append("stat(%d) does not read the latched mouse" % n)
    # NO FAKE POINTER, and "no pointer" spelled the only way p8 can spell it:
    # OFF THE SCREEN. A cart reads a position as a cursor that is THERE --
    # `dungeons & diagrams` takes `x > 8 and y > 8` for "over the board" and
    # then re-asserts its board cursor from it every frame, after its own
    # buttons have moved it -- so a phantom anywhere on the 128x128 stamps over
    # the d-pad. The corpus gate caught that; this is the cheaper net.
    if "local P8_MOUSE_AWAY = -8" not in shim:
        FAIL.append("the shim has no off-screen park for an absent pointer")
    if "local p8_mx, p8_my, p8_mb = P8_MOUSE_AWAY, P8_MOUSE_AWAY, 0" not in shim:
        FAIL.append("the mouse does not start away -- a cart with no pointer "
                    "is being handed a phantom one")
    # ...and it goes back there when the pointer expires, rather than freezing:
    # a touch console cannot move the finger off the board, so the CONSOLE has
    # to, or a cart that gates on the cursor never gets its buttons back.
    body = _lua_body(shim, "p8_mouse_tick").replace("L_", "")
    if "p8_mx,p8_my,p8_mb=P8_MOUSE_AWAY,P8_MOUSE_AWAY,0" not in body:
        FAIL.append("an absent pointer freezes the mouse instead of parking it")

    # THE MANIFEST HINT (SPEC.md 7.3), off either spelling of asking.
    for src, want in (("function _update() x=stat(32) end", True),
                      ("function _init() poke(0x5f2d,1) end", True),
                      ("function _update() x=stat(6) end", False),
                      ("function _update() x=btn(0) end", False)):
        got = p8_lua_port._reads_mouse(p8_lua_port._strip_lua(convert(src)))
        if got != want:
            FAIL.append("_reads_mouse(%r) answered %s" % (src, got))
    man = p8_lua_port.build_manifest("t", mouse=True)["input"]
    if "touch" not in man:
        FAIL.append("a mouse cart's manifest does not declare touch: %r" % man)
    if "touch" in p8_lua_port.build_manifest("t")["input"]:
        FAIL.append("a cart that never asks for a pointer declares touch")


def dialect():
    """The four p8 spellings a featured cart turned up that Lua cannot read.

    Every one of these came off the carts on PICO-8's own front page, and
    three of the four were SILENT: the output parsed and ran, as something
    else.
    """
    # `//` is a p8 line comment, and p8 has no `//` operator to confuse it
    # with -- integer divide there is `\`. Lua 5.4 has the operator and not
    # the comment, so this was a division (`42930` writes 105 of them).
    emits("a // comment", "// room faff", "-- room faff")
    emits("a trailing // comment", "x=1 // why", "x=1 -- why")
    emits("// inside a -- comment", "-- see https://x", "-- see https://x")
    emits("// inside a string", 'x="a//b"', 'x="a//b"')

    # p8 reads a high byte as a LETTER, so a glyph beside a name is part of
    # that name -- `loop` writes `p1<right>`, `hwd elite dock` `<x>_down` --
    # and a glyph ALONE is the value, which is what `squiddy` assigns to and
    # `fillp(<shade>)` wants.
    emits("a glyph inside a name", "p1\x91={1}", "p1_p8g145={1}")
    emits("a glyph opening a name", "\x97_down=0", "_p8g151_down=0")
    emits("a glyph alone is a value", "if btn(\x91) then x=1 end",
          "if btn(_p8g145) then x=1 end")
    emits("a glyph alone is assignable", "\x91=5", "_p8g145=5")

    # `if cond do`, at a bracket depth the line did not open. A minified cart
    # closes the line above's parens first (`libryinth`), and a callback on
    # one line never comes back to zero at all.
    emits("if..do under unbalanced parens", ")) if e0 do x=1 end",
          ")) if e0 then x=1 end")
    emits("if..do inside a callback", "f(function() if x do y=1 end end)",
          "f(function() if x then y=1 end end)")
    emits("a for's do is not an if's", "if a do for i=1,2 do z=1 end end",
          "if a then for i=1,2 do z=1 end end")
    emits("a while's do is its own", "while a do x=1 end", "while a do x=1 end")

    # `?` prints the rest of the LINE, and a long string outlives the line it
    # opened on: `gift guardian` closes the string and its remaining arguments
    # on the next one, where the paren belongs.
    got = convert('?[[bY nERDY\n tEACHERS]],90,20,5\nend').strip()
    want = 'print([[bY nERDY\n tEACHERS]],90,20,5)\nend'
    if got != want:
        FAIL.append("? over a long string: wanted %r, got %r" % (want, got))
    emits("? still ends before a block keyword", 'if a then ?"x",1 end',
          'if a then print("x",1) end')


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
    # THE WHOLE SUFFIX CHAIN on the left, mixed in any order. A walk that knew
    # `a.b.c` and `a[1]` but not the two together stopped at the last field and
    # let the call land INSIDE the expression -- `libryinth`'s
    # `T[2].ready << 1` came out as `T[2].__p8_shl(ready, 1)`, which parses,
    # runs, and is not what the cart wrote.
    emits("an index then a field", "x=a[1].b<<1", "x=__p8_shl(a[1].b, 1)")
    emits("a call then a field", "x=f(1).b<<1", "x=__p8_shl(f(1).b, 1)")
    emits("fields either side of an index", "x=t.a[1].b.c<<1",
          "x=__p8_shl(t.a[1].b.c, 1)")
    emits("a method call", "x=t:m(1)<<1", "x=__p8_shl(t:m(1), 1)")
    emits("a chained call", "x=f(1)(2)<<1", "x=__p8_shl(f(1)(2), 1)")
    emits("a chained index", "x=t[1][2]<<1", "x=__p8_shl(t[1][2], 1)")
    # ...and the keyword that is not a callee, which is what the bracket walk
    # has to keep refusing: `band(return (a), 1)` was a real output.
    emits("a keyword is not a callee", "return (a)&1",
          "return __p8_band((a), 1)")
    emits("a parenthesised operand", "x=(a+b)<<1", "x=__p8_shl((a+b), 1)")

    # p8's `\` is a MULTIPLICATIVE operator, left-associative beside `*`, `/`
    # and `%` -- not something that takes the primary either side of it. Both
    # of the first two were silent: they parsed, ran, and answered something
    # else. `crimson_night` unpacks its strings base-26 with the second.
    emits("`\` takes the whole product", "x=a*b\\c", "x=flr(a*b/c)")
    emits("`^` binds tighter than `\`", "x=v\\26^i%26+1",
          "x=flr(v/26^i)%26+1")
    emits("...and `*` on the right does not", "x=a\\b*c", "x=flr(a/b)*c")
    emits("`\` is left-associative", "x=a\\b\\c", "x=flr(flr(a/b)/c)")
    emits("`+` is looser either side", "x=1+a\\b+1", "x=1+flr(a/b)+1")
    emits("`..` is looser too", "x=a..b\\c", "x=a..flr(b/c)")
    emits("a length operand comes along", "x=#snd\\4", "x=flr(#snd/4)")
    emits("a minus on the right", "x=a\\-b", "x=flr(a/-b)")
    emits("an index and a product", "x=i\\2*128", "x=flr(i/2)*128")
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



# The nine bit verbs exist THREE times: in moy_p8.c, in the shim the porter
# emits, and transcribed into p8lib.moy as L_band/L_shr/... so run_cart can
# compare the machine against the Lua a host without one runs. p8lib pins the
# first two to each other; nothing pinned the third to the shim it claims to
# be, and while it was not, a wrong reading of `shr` sat green in both copies
# for weeks. This is that missing edge.
_TWINS = ("fx", "unfx", "is_int", "band", "bor", "bxor", "bnot",
          "shl", "shr", "lshr", "rotl", "rotr",
          # The TABLE verbs are the same three copies and were unpinned until
          # `libryinth` found the edge: p8's add takes an index, its del
          # answers with what it removed, and neither minds a nil table.
          "add", "del", "all", "foreach", "count", "deli")
_OPENS = ("function", "if", "do", "repeat")
_BLOCK = re.compile(r"\b(function|if|do|repeat|end|until)\b")


def _lua_clean(text):
    """Lua with its comments and string bodies out of the way."""
    text = re.sub(r"--\[\[.*?\]\]", " ", text, flags=re.S)
    text = re.sub(r"--[^\n]*", "", text)
    text = re.sub(r'"[^"\n]*"', '""', text)
    return re.sub(r"'[^'\n]*'", "''", text)


def _lua_body(text, name):
    """The body of `function NAME(` in `text`, comments and spacing gone."""
    clean = _lua_clean(text)
    m = re.search(r"\bfunction\s+%s\s*\(" % re.escape(name), clean)
    if not m:
        return None
    depth = 0
    for t in _BLOCK.finditer(clean, m.start()):
        if t.group(1) in _OPENS:
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return re.sub(r"\s+", "", clean[m.start():t.end()])
    return None


def bit_twins():
    """p8lib.moy's L_* really is the shim, modulo the prefix."""
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "p8lib.moy", "main.lua"), encoding="utf-8") as f:
        cart = f.read()
    for name in _TWINS:
        want = _lua_body(p8_lua_port.SHIM, name)
        got = _lua_body(cart, "L_" + name)
        if want is None:
            FAIL.append("the shim no longer defines %s" % name)
            continue
        if got is None:
            FAIL.append("p8lib.moy no longer transcribes %s as L_%s" % (name, name))
            continue
        if got.replace("L_", "") != want:
            FAIL.append("p8lib.moy's L_%s has drifted from the shim's %s:\n"
                        "  shim   %s\n  p8lib  %s"
                        % (name, name, want, got.replace("L_", "")))


if __name__ == "__main__":
    sys.exit(main())
