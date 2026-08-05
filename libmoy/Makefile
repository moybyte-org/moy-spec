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

SRC     := src/moy_canvas.c src/moy_sprite.c src/moy_data.c
OBJ     := $(SRC:.c=.o)
LIB     := libmoy.a
REPLAY  := build/trace_replay

.PHONY: all clean data conform test

all: $(LIB) $(REPLAY)

$(LIB): $(OBJ)
	$(AR) rcs $@ $^

%.o: %.c include/moy.h
	$(CC) $(CFLAGS) -c $< -o $@

$(REPLAY): test/trace_replay.c $(LIB)
	@mkdir -p build
	$(CC) $(CFLAGS) $< $(LIB) $(LDLIBS) -o $@

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

test: conform

clean:
	rm -f $(OBJ) $(LIB)
	rm -rf build
