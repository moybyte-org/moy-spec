# The web player build

These three files are the moy web player: a MicroPython-WASM build of the
reference console, frozen bytecode inside the .wasm, plus the page (a JS
replayer of the draw-command stream -- itself a complete implementation of
the SPEC.md verb raster). Fully static; a cart bundle beside them is a
playable game at a URL.

Built from the reference implementation (nikola-j/moybyte) at 76e337a,
via `firmware/web_runner/build.sh --spec` -- see that directory for the
recipe (emsdk + MicroPython v1.28 webassembly port + the moy_lua usermod).
Regenerate by rebuilding there and copying index.html + micropython.mjs +
micropython.wasm here. This will become a versioned release artifact once the
player stabilises.
