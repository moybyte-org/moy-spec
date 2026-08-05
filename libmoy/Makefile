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
# with io/os/debug/package/coroutine SOURCES removed, so the SPEC.md 4.1 sandbox
# has no reachable implementation to be re-exposed by accident.
LUA_DIR  := vendor/lua
LUA_SRC  := $(wildcard $(LUA_DIR)/*.c)
LUA_OBJ  := $(LUA_SRC:.c=.o)
LUA_CFLAGS := -std=c99 -O2 -w -I$(LUA_DIR)
RUNCART  := build/run_cart

.PHONY: all clean data conform conform-lua test lua play audio-test

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

$(RUNCART): test/run_cart.c src/moy_lua.o $(LUA_OBJ) $(LIB)
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

$(PLAY): port/sdl2/main.c src/moy_lua.o $(LUA_OBJ) $(LIB)
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

# The same suite through the REAL path: an actual .moy cart, parsed and run as
# Lua, rather than a recorded trace. This is what a finished host does, so it
# checks the binding and the sandbox as well as the raster.
conform-lua: $(RUNCART)
	cd $(SPEC) && python3 conformance/run.py --player \
	  "$(CURDIR)/build/run_cart {cart} {out}"

play: $(PLAY)

# SPEC.md 8's semantics, asserted numerically (8.3 exempts audio from pixel
# conformance, so this is its whole test story: pitch by zero crossings,
# envelopes by RMS, and the channel-claiming rules by inspection).
$(AUDIOT): test/audio_test.c $(LIB)
	@mkdir -p build
	$(CC) $(CFLAGS) $< $(LIB) $(LDLIBS) -o $@

audio-test: $(AUDIOT)
	./$(AUDIOT)

test: conform conform-lua audio-test

clean:
	rm -f $(OBJ) $(LUA_OBJ) src/moy_lua.o $(LIB)
	rm -rf build
