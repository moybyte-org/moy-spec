# The web player build

These three files are the moy web player: a MicroPython-WASM build of the
reference console, frozen bytecode inside the .wasm, plus the page (a JS
replayer of the draw-command stream -- itself a complete implementation of
the SPEC.md verb raster). Fully static; a cart bundle beside them is a
playable game at a URL.

Built from the reference implementation
([moybyte-org/moybyte](https://github.com/moybyte-org/moybyte)) at its web-runner tree (see its git log),
via `firmware/web_runner/build.sh --spec` -- see that directory for the
recipe (emsdk + MicroPython v1.28 webassembly port + the moy_lua usermod).
Regenerate by rebuilding there and copying index.html + micropython.mjs +
micropython.wasm here. This will become a versioned release artifact once the
player stabilises.

## Licensing of these artifacts

The reference implementation's source is FSL-1.1-MIT (source-available;
plain MIT per release after two years). These COMPILED artifacts are granted
under this repository's MIT license by the copyright holder, so the player can
be embedded and redistributed without friction -- the spec is only useful if
its player is. Third-party components inside the build are listed in
THIRD_PARTY.md (their notices ride along as those licenses require).
