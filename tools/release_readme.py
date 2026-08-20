#!/usr/bin/env python3
"""The text file that ships inside each release download -- generated, not typed.

    python3 tools/release_readme.py windows-player > dist-win/README.txt
    python3 tools/release_readme.py windows        > win/README.txt
    python3 tools/release_readme.py unix           > README.txt

This exists because the same few sentences -- above all the control legend -- used
to live in three `printf` heredocs inside .github/workflows/libmoy.yml plus a
sentence in README.md, and all four had drifted apart:

    "Arrows = d-pad, Z/X = A/B, Enter = run, Esc = quit"          (no WASD, no J/K)
    "Arrows/WASD = d-pad, Z/X (or J/K) = A/B, Enter = run, ..."   (two of them)

and NONE of the four mentioned that Space also works as `run`, which
port/sdl2/main.c has bound the whole time (its scancode table pairs LEFT/A,
RIGHT/D, UP/W, DOWN/S, Z/J, X/K, RETURN/SPACE). Four copies produced three
different wrong answers, which is the argument for one copy. `tools/check_docs.py`
asserts README.md still quotes the string below verbatim.

The line-ending split is deliberate: the Windows bundles are read in Notepad by
people who did not ask for a text-encoding adventure, so those get CRLF.
"""

import sys

# The one copy. port/sdl2/main.c is where the bindings actually are; if that
# table changes, change this line -- and check_docs.py will fail README.md until
# it agrees.
CONTROLS = ("Arrows or WASD = d-pad, Z/J = A, X/K = B, "
            "Enter or Space = run, Esc = quit.")

REPO = "https://github.com/moybyte-org/moy-spec"

# The player alone, cross-compiled by the mingw job and zipped with the CLI later.
WINDOWS_PLAYER = """\
moy-play -- the moy console as a Windows program.

Run a cart:  drag a .moy cart folder onto moy-play.exe,
or from a terminal:  moy-play.exe path\\to\\game.moy

{controls}

Spec and tools: {repo}
"""

WINDOWS = """\
moy -- the toy console, bundled for Windows.

moy-play.exe   the native player: drag a .moy cart folder onto it.
               {controls}
moy.exe        the whole toolchain, no Python needed: `moy demo` (fetches
               and ports Celeste Classic, then plays it in moy-play.exe),
               `moy new mygame`, `moy play mygame.moy` (hot reload: save a
               file, the game restarts), `moy web` for the browser player,
               check, pack, gfx/map PNG+CSV round-trips, conform, push. Run
               `moy` with no arguments for the full list.

Spec and source: {repo}
"""

UNIX = """\
moy -- the toy console: the CLI and the native player.

  ./moy demo                fetch Celeste Classic, port it, play it in moy-play
  ./moy new mygame          scaffold a cart
  ./moy play mygame.moy     play it -- and reload it every time you save
  ./moy web mygame.moy      the same, in the browser player
  ./moy                     the full command list

{controls}

macOS note: the binaries are unsigned -- first run is right-click -> Open,
or `xattr -d com.apple.quarantine moy moy-play`.

Spec and source: {repo}
"""

VARIANTS = {
    "windows-player": (WINDOWS_PLAYER, "\r\n"),
    "windows": (WINDOWS, "\r\n"),
    "unix": (UNIX, "\n"),
}


def main(argv):
    if len(argv) != 1 or argv[0] not in VARIANTS:
        sys.stderr.write("usage: release_readme.py {%s}\n"
                         % "|".join(sorted(VARIANTS)))
        return 2
    body, eol = VARIANTS[argv[0]]
    text = body.format(controls=CONTROLS, repo=REPO)
    sys.stdout.write(text.replace("\n", eol) if eol != "\n" else text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
