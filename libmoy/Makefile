# libmoy -- the moy console as a C library.
#
#   make            build libmoy.a and the trace replayer
#   make conform    run the conformance suite against it
#   make data       regenerate the embedded palette + font from the spec
#
# This lives INSIDE moy-spec, so the spec is the parent directory and there is
# nothing to point at: the conformance suite that checks this library and the
# palette.json and font.bin it compiles in are the ones directly above.

SPEC    ?= ..
CC      ?= cc
# -Wconversion is on deliberately. This is a raster: every bug it catches is a
# coordinate or a colour silently changing width, which is exactly the class of
# thing that produces a frame that looks fine and fails conformance by one pixel.
CFLAGS  ?= -std=c99 -O2 -Wall -Wextra -Wpedantic -Wshadow -Wconversion \
           -Wstrict-prototypes -Iinclude
LDLIBS  ?= -lm

SRC     := src/moy_canvas.c src/moy_sprite.c src/moy_data.c src/moy_audio.c
OBJ     := $(SRC:.c=.o)
LIB     := libmoy.a
REPLAY  := build/trace_replay
AUDIOT  := build/audio_test

# The Lua binding is optional and off by default: libmoy binds to whatever
# lua_State you hand it, so the VM is a build-time choice, not a dependency.
# vendor/lua is upstream Lua 5.4.7 with LUA_32BITS already set -- which SPEC.md
# 4.2 requires and SPEC.md 11 assumes of the build that generates goldens -- and
# with io/os/debug/package SOURCES removed, so the SPEC.md 4.1 sandbox
# has no reachable implementation to be re-exposed by accident.
LUA_DIR  := vendor/lua
LUA_SRC  := $(wildcard $(LUA_DIR)/*.c)
LUA_OBJ  := $(LUA_SRC:.c=.o)
LUA_CFLAGS := -std=c99 -O2 -w -I$(LUA_DIR)
RUNCART  := build/run_cart

.PHONY: all clean data conform conform-lua test lua play audio-test p8-carts

all: $(LIB) $(REPLAY)

lua: $(RUNCART)

$(LIB): $(OBJ)
	$(AR) rcs $@ $^

%.o: %.c include/moy.h include/moy_audio.h
	$(CC) $(CFLAGS) -c $< -o $@

$(REPLAY): test/trace_replay.c $(LIB)
	@mkdir -p build
	$(CC) $(CFLAGS) $< $(LIB) $(LDLIBS) -o $@

# Lua objects build with -w: it is upstream code and its warnings are not ours
# to fix. libmoy's own sources keep the full warning set.
$(LUA_DIR)/%.o: $(LUA_DIR)/%.c
	$(CC) $(LUA_CFLAGS) -c $< -o $@

src/moy_lua.o: src/moy_lua.c include/moy.h
	$(CC) $(CFLAGS) -DMOY_WITH_LUA -I$(LUA_DIR) -c $< -o $@

# The PICO-8 machine (src/moy_p8.c): host verbs for ported carts, opt-in,
# and Lua-shaped like the binding, so it builds with it.
src/moy_p8.o: src/moy_p8.c include/moy.h src/moy_pixel.h
	$(CC) $(CFLAGS) -DMOY_WITH_LUA -I$(LUA_DIR) -c $< -o $@

$(RUNCART): test/run_cart.c src/moy_lua.o src/moy_p8.o $(LUA_OBJ) $(LIB)
	@mkdir -p build
	$(CC) $(CFLAGS) -DMOY_WITH_LUA -I$(LUA_DIR) $^ $(LDLIBS) -o $@

# The desktop port: a playable console in ~250 lines of SDL2, and the worked
# example of what a platform actually owes libmoy. Built only on request, so the
# library itself keeps its no-dependencies claim -- SDL2 is never needed to build
# libmoy.a, run conformance, or ship this repository's CI.
#
# Assigned HERE, above the rule, and not further down: make expands variables in
# a target line as it READS the file, so a `$(PLAY):` rule above this assignment
# expands to an empty target and is silently dropped. `make play` then fails with
# "no rule to make target", which is how this was found.
PLAY := build/moy-play

$(PLAY): port/sdl2/main.c src/moy_lua.o src/moy_p8.o $(LUA_OBJ) $(LIB)
	@mkdir -p build
	$(CC) $(CFLAGS) -DMOY_WITH_LUA -I$(LUA_DIR) $^ \
	  $(shell pkg-config --cflags --libs sdl2) $(LDLIBS) -o $@

# The palette and font are the spec's, not ours (SPEC.md 2 and 6 make both data
# rather than prose so implementations cannot drift). Regenerated, never typed
# -- and from the copy one directory up, so there is no version to keep in step.
data:
	python3 tools/embed_data.py --spec $(SPEC)

# The whole point. Runs the repository's own conformance runner against this
# library, so libmoy is checked by the same golden frames as the reference
# console, the WebAssembly player and an ESP32-P4 -- not by a test suite of its
# own devising. Living in the same repo means a spec change that breaks the C
# core turns the same CI red on the same push.
conform: all
	cd $(SPEC) && python3 conformance/run.py --player \
	  "$(CURDIR)/test/replay_cart.sh {cart} {out}"

# The SAME suite against the direct-colour build (MOY_PIXEL_RGB565): identical
# geometry, colour resolved at draw time into a 16-bit buffer instead of at
# flush. The replayer resolves back to indices before writing, so both builds
# are judged by the same goldens -- which is the only thing that makes the
# pixel format a host's choice (SPEC.md 1.1) rather than a fork of the raster.
BUILD565 := build/565
conform-565:
	@mkdir -p $(BUILD565)
	$(CC) $(CFLAGS) -DMOY_PIXEL_RGB565 -o $(BUILD565)/trace_replay \
	  test/trace_replay.c $(SRC) $(LDLIBS)
	cd $(SPEC) && MOY_REPLAY="$(CURDIR)/$(BUILD565)/trace_replay" \
	  python3 conformance/run.py --player \
	  "$(CURDIR)/test/replay_cart.sh {cart} {out}"

# The same suite through the REAL path: an actual .moy cart, parsed and run as
# Lua, rather than a recorded trace. This is what a finished host does, so it
# checks the binding and the sandbox as well as the raster.
conform-lua: $(RUNCART)
	cd $(SPEC) && python3 conformance/run.py --player \
	  "$(CURDIR)/build/run_cart {cart} {out}"

# The PORTER, against real PICO-8 carts, on THIS VM. p8_lua_port.py lives in
# this repository and hosts vendor it, so a bug introduced here is otherwise
# only noticed at the next re-vendor -- the same delay this Makefile's
# conform-lua target exists to close for the C. And the VM matters: LUA_32BITS
# makes lua_Number a single-precision float, so a desktop Lua cannot stand in.
#
# Skips without a corpus: the carts are their authors' work and are not
# redistributed. Point MOY_P8_CORPUS at a directory of .p8 / .p8.png files.
p8-carts: $(RUNCART)
	cd $(SPEC) && python3 conformance/p8_carts.py

play: $(PLAY)

# SPEC.md 8's semantics, asserted numerically (8.3 exempts audio from pixel
# conformance, so this is its whole test story: pitch by zero crossings,
# envelopes by RMS, and the channel-claiming rules by inspection).
EXTT    := build/ext_test

# SPEC.md 10's extensions need the Lua binding, hence moy_lua.o and the VM --
# the audio test above needs neither, which is why they are separate targets.
$(EXTT): test/ext_test.c src/moy_lua.o src/moy_p8.o $(LUA_OBJ) $(LIB)
	@mkdir -p build
	$(CC) $(CFLAGS) -DMOY_WITH_LUA -I$(LUA_DIR) $^ $(LDLIBS) -o $@

ext-test: $(EXTT)
	./$(EXTT)

$(AUDIOT): test/audio_test.c $(LIB)
	@mkdir -p build
	$(CC) $(CFLAGS) $< $(LIB) $(LDLIBS) -o $@

audio-test: $(AUDIOT)
	./$(AUDIOT)

# A declared canvas (SPEC.md 3.1) resizes the raster: the cart itself asserts
# W/H, and the dumped frame must be exactly 160x120 bytes.
lowres: $(RUNCART)
	./$(RUNCART) test/lowres.moy build/lowres.bin --frames 1
	@test "$$(wc -c < build/lowres.bin)" -eq 19200 \
	  && echo "lowres: 160x120 frame is 19200 bytes" \
	  || { echo "lowres: frame is $$(wc -c < build/lowres.bin) bytes, want 19200"; exit 1; }

# spr at scale > 1 against the kernel it replaced. The conformance scenes cover
# scale 3 with all four flips, but only unclipped at the origin -- and the whole
# risk of the hoisted rewrite is the CLIPPED edge, where the destination loop
# starts mid-source-pixel. So sweep every scale 2..5 x flip x colorkey x palt
# across four clip windows and three camera offsets, straddling every edge and
# corner, against the original moy_rect form transcribed verbatim. 708k cases;
# any single differing byte fails.
SPRSWEEP := build/spr_scale_sweep
$(SPRSWEEP): test/spr_scale_sweep.c $(LIB)
	@mkdir -p build
	$(CC) $(CFLAGS) $< $(LIB) $(LDLIBS) -o $@

spr-sweep: $(SPRSWEEP)
	./$(SPRSWEEP)

# The PICO-8 machine: a cart asserts every mirrored region of the memory map
# both ways (test/p8mem.moy), the C font is held equal to the shim's, the
# stdlib verbs promoted out of the shim are held equal to the Lua they replace
# (test/p8lib.moy) -- a cart may reach either lane, so there is one answer --
# and the port's first frame is checked at a period SHORTER than one cart tick,
# which is the only place _draw can outrun _update (test/p8_first_draw.py).
# p8_port_check.py is the PORTER's half: the statement shapes it folds, and the
# near misses it must leave alone, which no corpus cart can be relied on to
# contain.
p8-test: $(RUNCART)
	./$(RUNCART) test/p8mem.moy build/p8mem.bin --frames 2
	./$(RUNCART) test/p8lib.moy build/p8lib.bin --frames 2
	python3 test/p8_font_check.py
	python3 test/p8_first_draw.py
	python3 test/p8_port_check.py

test: conform conform-lua ext-test audio-test lowres spr-sweep p8-test p8-carts

clean:
	rm -f $(OBJ) $(LUA_OBJ) src/moy_lua.o src/moy_p8.o $(LIB)
	rm -rf build
