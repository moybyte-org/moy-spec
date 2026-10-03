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

.PHONY: all clean data conform conform-lua test lua play audio-test p8-carts float-fold sources-test wasm-check wasm-test wasm-table wamr compiled-test compiled-test-offline cover-test

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

# SPEC.md 4's `sources`: load order, chunk isolation, and the refusals. Driven
# through run_cart because the claim is about the LOADER, not the raster -- a
# host that concatenated the scripts would render every golden perfectly.
sources-test: $(RUNCART)
	bash test/sources_test.sh ./$(RUNCART)

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

# The machine's number coercion, held equal to the double-precision form it
# replaced over the float bit patterns -- the change that moved it into
# lua_Number, because neither board has a double FPU and every promote was a
# libgcc call. Standalone (both sides are static in moy_p8.c and one no longer
# exists), so it needs no libmoy. The default stride sweeps ~116M patterns in a
# few seconds; `./build/p8_float_fold 1` is the exhaustive 2^32 form, ~2 min.
FLOATFOLD := build/p8_float_fold
$(FLOATFOLD): test/p8_float_fold.c
	@mkdir -p build
	$(CC) $(CFLAGS) $< $(LDLIBS) -o $@

float-fold: $(FLOATFOLD)
	./$(FLOATFOLD)

# The PICO-8 machine: a cart asserts every mirrored region of the memory map
# both ways (test/p8mem.moy), the C font is held equal to the shim's, the
# stdlib verbs promoted out of the shim are held equal to the Lua they replace
# (test/p8lib.moy) -- a cart may reach either lane, so there is one answer --
# and the port's first frame is checked at a period SHORTER than one cart tick,
# which is the only place _draw can outrun _update (test/p8_first_draw.py).
# p8_port_check.py is the PORTER's half: the statement shapes it folds, and the
# near misses it must leave alone, which no corpus cart can be relied on to
# contain. p8_label_check.py pins where a .p8.png keeps its label, which
# becomes the port's cover.png.
p8-test: $(RUNCART) $(FLOATFOLD)
	./$(FLOATFOLD)
	./$(RUNCART) test/p8mem.moy build/p8mem.bin --frames 2
	./$(RUNCART) test/p8lib.moy build/p8lib.bin --frames 2
	python3 test/p8_font_check.py
	python3 test/p8_first_draw.py
	python3 test/p8_port_check.py
	python3 test/p8_label_check.py

# The wasm binding (src/moy_wasm.c, SPEC.md 16) under WAMR.
# WAMR is the one thing here fetched from the network, by this target and by
# `play`: it is not a libmoy dependency and is not vendored, so this clones the
# fork the reference console pins, AT THE PIN, into build/wamr/ (gitignored,
# like all of build/) and builds its interpreter with no WASI and no builtin
# libc -- imports from "moy" are the only ones a cart has. The binding needs the
# direct-colour build, so libmoy compiles again with MOY_PIXEL_RGB565 beside
# MOY_WASM. The fixtures are WAT, assembled by tools/wat.py; the harness runs
# them and test/wasm_frame.py holds the frame against moycore's rendering.
WAMR_REPO  ?= https://github.com/moybyte-org/wasm-micro-runtime.git
WAMR_PIN   ?= a7b71791f0e7b36e34d7d8abaef57b1d64d6f8e7
WAMR_SRC   := build/wamr/src
# WAMR's own platform directory for this machine, or for a cross build the
# caller names with WAMR_PLATFORM=windows and a toolchain in WAMR_CMAKE_FLAGS.
WAMR_PLATFORM ?= $(if $(filter Darwin,$(shell uname -s)),darwin,linux)
WAMR_CMAKE_FLAGS ?=
WAMR_BUILD := build/wamr/$(WAMR_PLATFORM)
# On Windows WAMR's hardware bound check is MSVC's structured exceptions, which
# a MinGW build has not; the interpreter checks every access in software.
WAMR_PLATFORM_FLAGS := $(if $(filter windows,$(WAMR_PLATFORM)),-DWAMR_DISABLE_HW_BOUND_CHECK=1)
WAMR_LIB   := $(WAMR_BUILD)/$(if $(filter windows,$(WAMR_PLATFORM)),liblibiwasm.a,libiwasm.a)
# What libiwasm.a needs from the system. On Windows its clock is MinGW's
# winpthreads, linked in statically so the player ships with SDL2.dll alone.
WAMR_LIBS_linux   := -lpthread -ldl
WAMR_LIBS_darwin  := -lpthread
WAMR_LIBS_windows := -lws2_32 -lntdll -Wl,-Bstatic -lwinpthread -Wl,-Bdynamic
WAMR_LIBS  := $(WAMR_LIBS_$(WAMR_PLATFORM))
WASMT      := build/wasm_test

$(WAMR_SRC)/.pin-$(WAMR_PIN):
	rm -rf $(WAMR_SRC) && mkdir -p $(WAMR_SRC)
	git -C $(WAMR_SRC) init -q
	git -C $(WAMR_SRC) fetch -q --depth 1 $(WAMR_REPO) $(WAMR_PIN)
	git -C $(WAMR_SRC) checkout -q FETCH_HEAD
	test "$$(git -C $(WAMR_SRC) rev-parse HEAD)" = "$(WAMR_PIN)"
	touch $@

# WAMR builds with its own flags: make exports a command-line CFLAGS to the
# recipe's environment, and cmake would hand this repo's -Werror set to WAMR.
$(WAMR_LIB): $(WAMR_SRC)/.pin-$(WAMR_PIN)
	env -u CFLAGS -u CXXFLAGS cmake -S $(WAMR_SRC)/product-mini/platforms/$(WAMR_PLATFORM) -B $(WAMR_BUILD) \
	  -DCMAKE_BUILD_TYPE=Release -DWAMR_BUILD_INTERP=1 -DWAMR_BUILD_AOT=0 \
	  -DWAMR_BUILD_JIT=0 -DWAMR_BUILD_FAST_JIT=0 -DWAMR_BUILD_LIBC_BUILTIN=0 \
	  -DWAMR_BUILD_LIBC_WASI=0 -DWAMR_BUILD_SIMD=0 $(WAMR_PLATFORM_FLAGS) $(WAMR_CMAKE_FLAGS) \
	  > build/wamr/cmake-$(WAMR_PLATFORM).log
	env -u CFLAGS -u CXXFLAGS cmake --build $(WAMR_BUILD) --target vmlib -j4 > build/wamr/build-$(WAMR_PLATFORM).log

wamr: $(WAMR_LIB)

$(WASMT): test/wasm_test.c src/moy_wasm.c include/moy_wasm.h port/moy_lanes.c port/moy_lanes.h \
          port/moy_files.c port/moy_files.h port/moy_manifest.h $(SRC) include/moy.h $(WAMR_LIB)
	$(CC) $(CFLAGS) -DMOY_PIXEL_RGB565 -DMOY_WASM \
	  -isystem $(WAMR_SRC)/core/iwasm/include \
	  test/wasm_test.c src/moy_wasm.c port/moy_lanes.c port/moy_files.c $(SRC) $(WAMR_LIB) \
	  -lm $(WAMR_LIBS) -o $@

wasm-test: $(WASMT)
	rm -rf build/wasm && mkdir -p build/wasm
	for d in test/wasm/*.moy; do \
	  python3 ../tools/wat.py --cart $$d build/wasm/$$(basename $$d) || exit 1; done
	for f in test/wasm/*.wat; do \
	  python3 ../tools/wat.py $$f build/wasm/$$(basename $$f .wat).wasm || exit 1; done
	./$(WASMT) build/wasm build/wasm/hello.bin
	python3 test/wasm_frame.py build/wasm/hello.bin

# The desktop port: a playable console in a few hundred lines of SDL2, and the
# worked example of what a platform actually owes libmoy. Built only on
# request, so the library itself keeps its no-dependencies claim -- SDL2 is
# never needed to build libmoy.a, run conformance, or ship this repository's CI.
#
# It runs compiled carts too (port/sdl2/wasm_cart.c): libmoy's wasm binding
# over WAMR's interpreter, which is why this rule sits below the WAMR block and
# fetches the pinned fork like wasm-test does. The binding needs the
# direct-colour raster and the Lua carts keep the index one, so the raster is
# compiled a second time under its moy565_ names (port/moy565.h) and both
# link. PLAY_WASM=0 builds a player without it, which refuses a compiled cart
# as SPEC.md 3.1 says. SDL_FLAGS and PLAY name a cross build's SDL and binary.
#
# Assigned HERE, above the rule: make expands variables in a target line as it
# READS the file, so a `$(PLAY):` rule above this assignment expands to an
# empty target and is silently dropped. `make play` then fails with "no rule
# to make target", which is how this was found.
PLAY      := build/moy-play
PLAY_WASM ?= 1
SDL_FLAGS ?= $(shell pkg-config --cflags --libs sdl2)
P565      := build/play565
P565_CFLAGS = $(CFLAGS) -DMOY_PIXEL_RGB565 -DMOY_WASM -include port/moy565.h \
              -isystem $(WAMR_SRC)/core/iwasm/include
ifeq ($(PLAY_WASM),1)
PLAY_WASM_OBJ  := $(P565)/moy_canvas.o $(P565)/moy_sprite.o $(P565)/moy_wasm.o \
                  $(P565)/wasm_cart.o $(P565)/moy_lanes.o $(P565)/moy_files.o
PLAY_WASM_LINK := $(WAMR_LIB) $(WAMR_LIBS)
PLAY_WASM_DEF  := -DMOY_PLAY_WASM
endif

$(P565)/%.o: src/%.c include/moy.h include/moy_wasm.h src/moy_pixel.h port/moy565.h \
             $(WAMR_SRC)/.pin-$(WAMR_PIN)
	@mkdir -p $(P565)
	$(CC) $(P565_CFLAGS) -c $< -o $@

$(P565)/wasm_cart.o: port/sdl2/wasm_cart.c port/sdl2/wasm_cart.h include/moy.h \
                     include/moy_wasm.h port/moy565.h port/moy_lanes.h port/moy_files.h \
                     $(WAMR_SRC)/.pin-$(WAMR_PIN)
	@mkdir -p $(P565)
	$(CC) $(P565_CFLAGS) -c $< -o $@

$(P565)/moy_lanes.o: port/moy_lanes.c port/moy_lanes.h include/moy_wasm.h \
                     $(WAMR_SRC)/.pin-$(WAMR_PIN)
	@mkdir -p $(P565)
	$(CC) $(P565_CFLAGS) -c $< -o $@

$(P565)/moy_files.o: port/moy_files.c port/moy_files.h include/moy_wasm.h \
                     $(WAMR_SRC)/.pin-$(WAMR_PIN)
	@mkdir -p $(P565)
	$(CC) $(P565_CFLAGS) -c $< -o $@

$(PLAY): port/sdl2/main.c port/sdl2/wasm_cart.h port/moy_manifest.h src/moy_lua.o \
         src/moy_p8.o $(LUA_OBJ) $(LIB) $(PLAY_WASM_OBJ) $(if $(PLAY_WASM_OBJ),$(WAMR_LIB))
	@mkdir -p build
	$(CC) $(CFLAGS) -DMOY_WITH_LUA $(PLAY_WASM_DEF) -I$(LUA_DIR) \
	  port/sdl2/main.c src/moy_lua.o src/moy_p8.o $(LUA_OBJ) $(PLAY_WASM_OBJ) $(LIB) \
	  $(PLAY_WASM_LINK) $(SDL_FLAGS) $(LDLIBS) -o $@

play: $(PLAY)

# `moy check` on compiled carts (SPEC.md 16): the fixtures in
# test/wasm/ are WAT source, assembled by tools/wat.py with nothing but
# Python, and each is refused -- or, for hello.moy, passed -- through the real
# CLI. No WAMR and no compiler: this is the half every checkout can run.
wasm-check:
	python3 test/wasm_check_test.py

# The wasm import table (wasm-imports.json) is the verb table the Lua
# binding installs plus the wasm binding's own six, and src/moy_wasm.c
# registers exactly its rows at its signatures. Parsed, not compiled, so it
# needs no WAMR.
wasm-table:
	python3 test/wasm_table_check.py

# The compiled-cart authoring loop (compiled.py, cartindex.py): `moy new
# --wasm`, `moy pack`, `moy index` and `moy install` with Python alone, then
# both starters built with the pinned wasi-sdk (fetched by sha256 once, into
# moy's data directory), held to SPEC.md 16 and played in moy-play when it is
# built, and `moy build` refusing what it should. `compiled-test-offline` is
# the half that needs no toolchain and no network.
compiled-test:
	python3 test/compiled_test.py

compiled-test-offline:
	python3 test/compiled_test.py --offline

# SPEC.md 3.6's covers: moycore's reader against conformance/covers/, the
# writer and the squaring the CLI's F7, `moy build` and the importer use.
# Python only.
cover-test:
	python3 test/cover_test.py

test: conform conform-lua ext-test sources-test audio-test lowres spr-sweep p8-test p8-carts wasm-check wasm-table compiled-test-offline cover-test

clean:
	rm -f $(OBJ) $(LUA_OBJ) src/moy_lua.o src/moy_p8.o $(LIB)
	rm -rf build
