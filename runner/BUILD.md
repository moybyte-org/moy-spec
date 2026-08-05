# The web player build

These three files are the moy web player: a MicroPython-WASM build of the
reference console, frozen bytecode inside the .wasm, plus the page (a JS
replayer of the draw-command stream -- itself a complete implementation of
the SPEC.md verb raster). Fully static; a cart bundle beside them is a
playable game at a URL.

These files are PINNED, not copied by hand. `runner/VERSION` records which
build they are -- source commit, branch, and a sha256 per file -- and

    python3 moy.py player            # what this is, and do the files still match
    python3 moy.py player --update   # move the pin to the latest release

is how it moves. So updating the player is an ordinary reviewable commit rather
than an opaque blob swap, and "which player is this?" has an answer in the tree.

The releases come from the reference implementation
([moybyte-org/moybyte](https://github.com/moybyte-org/moybyte)), built by
`firmware/web_runner/build.sh --spec` (emsdk + MicroPython v1.28 webassembly
port + the moy_lua usermod) and published per branch by its `web-player`
workflow: `player-latest` from master, `player-beta` from dev.

**Each release is conformance-gated.** That workflow runs THIS repository's
suite against the bundle it just built and refuses to publish one that fails --
so `--update` cannot quietly hand you a player that disagrees with the goldens
it is supposed to be the tiebreaker for. `--from <dir>` pins a local build
instead, for anyone working on the player itself.

## Licensing of these artifacts

The reference implementation's source is FSL-1.1-MIT (source-available;
plain MIT per release after two years). These COMPILED artifacts are granted
under this repository's MIT license by the copyright holder, so the player can
be embedded and redistributed without friction -- the spec is only useful if
its player is. Third-party components inside the build are listed in
THIRD_PARTY.md (their notices ride along as those licenses require).
