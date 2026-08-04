"""Locating the normative data files (palette.json, font.bin).

Those two files are part of the SPEC, not part of this package -- SPEC.md 2 and
6 say so explicitly ("conformance needs exact values, so it is data, not
prose"). They live at the repository root beside SPEC.md, and moycore reads
them rather than carrying a second copy that could silently drift from the
normative one.

A copy placed inside the package still works, for the case where moycore is
vendored on its own (a frozen firmware image, a pip install). The search order
puts the repo root first so an in-tree checkout can never read a stale vendored
duplicate.

No os.path: MicroPython's os module is a subset, and this has to import there.
"""

_HERE = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."

# Repo root first (the normative location), then the package itself (vendored).
SEARCH = (_HERE + "/../", _HERE + "/", "./")


class DataError(Exception):
    """A normative data file is missing or malformed."""


def read(name, binary=False):
    """The bytes (or text) of normative data file `name`, from the first
    location that has it. Raises DataError naming every path tried -- a missing
    palette.json is a broken install, not something to paper over with a
    built-in fallback table (a silent fallback is exactly how two hosts end up
    disagreeing about colour 37)."""
    mode = "rb" if binary else "r"
    tried = []
    for base in SEARCH:
        path = base + name
        tried.append(path)
        try:
            f = open(path, mode)
        except OSError:
            continue
        try:
            return f.read()
        finally:
            f.close()
    raise DataError("%s not found; tried: %s" % (name, ", ".join(tried)))
