#!/usr/bin/env python3
"""What a list says about a cart (SPEC.md 3.7): description, genre and tags.

  * moycore.Cart reads each the way every host does, on the cases in
    conformance/listing.json: a genre off the list is no genre, a tag off the
    rule is dropped and the rest kept, the ninth tag on is not read, a
    description past 240 bytes is cut on a character boundary, and none of it
    ever refuses the cart.
  * `moy check`'s manifest checks warn on each of those, and on nothing a
    valid manifest says.
  * cartindex carries the three into an index entry as a host reads them, and
    check_index holds an entry to the same rules.
  * the PICO-8 importer writes the reserved tag `pico8` into the manifest of
    every cart it converts.
  * the examples, which show the fields in use, draw no finding for them.
  * SPEC.md's and GUIDE.md's genre lists, and SPEC.md's three bounds, are
    moycore's.

Run by `make manifest-test`.
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

import cartindex                                              # noqa: E402
import p8_import                                              # noqa: E402
import p8_lua_port                                            # noqa: E402
from moycore import cart as mcart                             # noqa: E402
from moycore import check as mcheck                           # noqa: E402

FAIL = []


def expect(what, got, want):
    if got != want:
        FAIL.append("%s: wanted %r, got %r" % (what, want, got))


def cart(**fields):
    man = {"format": "moy-1", "title": "T"}
    man.update(fields)
    return mcart.Cart.from_files({"manifest.json": json.dumps(man).encode("utf-8"),
                                  "main.lua": b"function _draw() cls(0) end\n"})


def codes(**fields):
    """The listing findings `moy check` gives a manifest with `fields`."""
    man = {"format": "moy-1", "title": "T"}
    man.update(fields)
    found = []
    mcheck.check_manifest(man, found)
    return [(level, code) for level, code, _ in found
            if code in ("manifest.description", "manifest.genre", "manifest.tags")]


def reading():
    """conformance/listing.json, through moycore.Cart -- what every host reads."""
    with open(os.path.join(ROOT, "conformance", "listing.json"), encoding="utf-8") as f:
        cases = json.load(f)["cases"]
    for case in cases:
        c = cart(**case["manifest"])
        expect(case["name"], (c.description, c.genre, c.tags),
               (case["description"], case["genre"], case["tags"]))
    for g in mcart.GENRES:
        expect("genre %r" % g, cart(genre=g).genre, g)


def checking():
    expect("valid fields", codes(description="Fine.", genre="puzzle",
                                 tags=["pico8", "two-player"]), [])
    expect("unknown genre", codes(genre="shmup"), [("warn", "manifest.genre")])
    expect("long description", codes(description="a" * 241),
           [("warn", "manifest.description")])
    expect("240 bytes", codes(description="a" * 240), [])
    expect("description not a string", codes(description=1),
           [("warn", "manifest.description")])
    expect("tags not an array", codes(tags="pico8"), [("warn", "manifest.tags")])
    expect("a bad tag", codes(tags=["ok", "Not-OK"]), [("warn", "manifest.tags")])
    expect("a repeated tag", codes(tags=["ok", "ok"]), [("warn", "manifest.tags")])
    expect("nine tags", codes(tags=["t%d" % i for i in range(9)]),
           [("warn", "manifest.tags")])
    # Cosmetic: nothing here is ever an error.
    expect("never an error", [lvl for lvl, _ in codes(
        description=3, genre=4, tags=["!"] * 9) if lvl == "error"], [])


def index():
    man = {"format": "moy-1", "title": "T", "description": "Line\none.",
           "genre": "Puzzle", "tags": ["pico8", "BAD", "pico8"]}
    expect("listing", cartindex.listing(man),
           {"description": "Line one.", "tags": ["pico8"]})
    expect("nothing to list", cartindex.listing({"format": "moy-1"}), {})

    def problems(**fields):
        entry = {"id": "a", "name": "A", "folder": "a.moy", "runtime": "lua",
                 "version": 1, "licence": {"url": "l", "size": 1, "sha256": "0" * 64},
                 "assets": [{"name": "a.zip", "url": "u", "size": 1, "sha256": "0" * 64,
                             "files": {}}]}
        entry.update(fields)
        return cartindex.check_index({"version": cartindex.INDEX_VERSION,
                                      "carts": [entry]})
    expect("a plain entry", problems(), [])
    expect("an entry with all three",
           problems(description="d", genre="rpg", tags=["pico8"]), [])
    for bad in ({"genre": "shmup"}, {"genre": None}, {"tags": ["A"]}, {"tags": []},
                {"tags": ["a", "a"]}, {"tags": "a"}, {"description": ""},
                {"description": "x" * 241}, {"tags": ["t%d" % i for i in range(9)]}):
        if len(problems(**bad)) != 1:
            FAIL.append("check_index passed or over-reported %r: %r" % (bad, problems(**bad)))

    # moy index writes them after the name, read from the manifest every run.
    tmp = tempfile.mkdtemp(prefix="moy-manifest-")
    try:
        os.makedirs(os.path.join(tmp, "carts", "a"))
        with open(os.path.join(tmp, "carts", "a", "manifest.json"), "w") as f:
            json.dump(man, f)
        entry = cartindex.with_listing(tmp, {"id": "a", "name": "A", "genre": "rpg",
                                             "version": 1})
        expect("with_listing", list(entry.items()),
               [("id", "a"), ("name", "A"), ("description", "Line one."),
                ("tags", ["pico8"]), ("version", 1)])
    finally:
        shutil.rmtree(tmp)


def importer():
    man = p8_lua_port.build_manifest("t")
    expect("build_manifest's tags", man.get("tags"), ["pico8"])
    tmp = tempfile.mkdtemp(prefix="moy-manifest-")
    try:
        out = os.path.join(tmp, "draw.moy")
        p8_lua_port.port_sections(
            p8_import.read_p8(os.path.join(HERE, "p8_draw_only.p8")), out, "draw")
        with open(os.path.join(out, "manifest.json"), encoding="utf-8") as f:
            written = json.load(f)
        expect("the ported manifest's tags", written.get("tags"), ["pico8"])
        loaded = mcart.load_cart(out)
        expect("the ported cart read back", loaded.tags, ["pico8"])
        expect("moy check on the ported manifest", codes(**written), [])
    finally:
        shutil.rmtree(tmp)


def examples():
    for name in sorted(os.listdir(os.path.join(ROOT, "examples"))):
        path = os.path.join(ROOT, "examples", name, "manifest.json")
        if not name.endswith(".moy") or not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            man = json.load(f)
        expect("examples/%s" % name, codes(**man), [])


def documents():
    """SPEC.md 3.7's genre table and GUIDE.md's list are moycore's GENRES."""
    import re
    with open(os.path.join(ROOT, "SPEC.md"), encoding="utf-8") as f:
        spec = f.read()
    table = spec.split("**`genre`** is exactly one of:", 1)[1].split("\n\n", 2)[1]
    expect("SPEC.md 3.7's genres", tuple(re.findall(r"^\| `([a-z]+)` \|", table, re.M)),
           mcart.GENRES)
    for said in ("**%d bytes**" % mcart.DESCRIPTION_MAX,
                 "**1 to %d characters" % mcart.TAG_MAX,
                 "at most **%d**" % mcart.TAGS_MAX):
        if said not in spec:
            FAIL.append("SPEC.md 3.7 does not say %r" % said)
    with open(os.path.join(ROOT, "GUIDE.md"), encoding="utf-8") as f:
        guide = f.read()
    listed = guide.split("`genre` is\none of ", 1)[1].split(" — ", 1)[0]
    expect("GUIDE.md's genres", tuple(re.findall(r"`([a-z]+)`", listed)), mcart.GENRES)


def main():
    documents()
    reading()
    checking()
    index()
    importer()
    examples()
    for line in FAIL:
        print("manifest: " + line)
    if FAIL:
        return 1
    print("manifest: description, genre and tags read, checked, indexed and "
          "imported as SPEC.md 3.7 says")
    return 0


if __name__ == "__main__":
    sys.exit(main())
