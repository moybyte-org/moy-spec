#!/usr/bin/env python3
"""What the web player is compiled from, and a digest of it.

    python3 libmoy/port/wasm/inputs.py [spec-root]   # -> one sha256

build.sh stamps this into runner/VERSION and `moy player` recomputes it, so the
question "is the committed bundle built from this source?" has an answer that
does not depend on git and cannot be written by hand.

It is here because the stamp's other provenance field could be, and was. Three
commits rewrote runner/VERSION's `source.commit` while runner/moy.wasm stayed
byte-identical -- the page files were updated in both places and the stamp went
with them -- so the bundle claimed a build it had never had. Meanwhile the
commit-based check needs history, and CI checks out shallow, so in the one place
it most needed to fire it could not see far enough to fire at all.

A digest of the inputs has neither problem: it is computed from the files on
disk, in a release binary or a one-commit clone alike.
"""

import glob
import hashlib
import os
import sys

# Every file that reaches emcc (see build.sh's SRC and the two page copies),
# plus build.sh itself -- change the flags and the output changes too.
PATTERNS = (
    "libmoy/src/*.c",
    "libmoy/include/*.h",
    "libmoy/vendor/lua/*.c",
    "libmoy/vendor/lua/*.h",
    "libmoy/port/wasm/main.c",
    "libmoy/port/wasm/page/*",
    "libmoy/port/wasm/build.sh",
)


def files(root):
    out = []
    for pat in PATTERNS:
        out.extend(sorted(glob.glob(os.path.join(root, pat))))
    return [f for f in out if os.path.isfile(f)]


def digest(root):
    """sha256 over every input's path and bytes, in a fixed order.

    Paths are included, so adding or removing a source changes the digest even
    when the surviving bytes do not."""
    h = hashlib.sha256()
    for path in files(root):
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        h.update(rel.encode("utf-8") + b"\0")
        with open(path, "rb") as f:
            h.update(hashlib.sha256(f.read()).digest())
    return h.hexdigest()


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "..", "..", "..")
    print(digest(os.path.abspath(root)))
