#!/usr/bin/env python3
"""An sfx's optional `name` (SPEC.md 8.1): a label that never changes playback.

  * moycore.Cart keeps sounds.json as written, so a tool that loads and writes
    it back carries every name (an empty one too).
  * moycore.sound_name reads a name the way every host does: a non-string is no
    name, one past 24 characters is cut to 24.
  * `moy check` warns on a non-string name and on a long one, and on nothing a
    valid bank says.
  * SPEC.md states the bound moycore holds.

The C reader's half (the name parses and never reaches the sound) is
audio_test.c. Run by `make sounds-test`.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

from moycore import cart as mcart                             # noqa: E402
from moycore import check as mcheck                           # noqa: E402

FAIL = []


def expect(what, got, want):
    if got != want:
        FAIL.append("%s: wanted %r, got %r" % (what, want, got))


def cart(bank):
    man = {"format": "moy-1", "title": "T"}
    return mcart.Cart.from_files({"manifest.json": json.dumps(man).encode("utf-8"),
                                  "main.lua": b"function _draw() cls(0) end\n",
                                  "sounds.json": json.dumps(bank).encode("utf-8")})


def sound_findings(bank):
    return [(level, code) for level, code, _ in mcheck.check_cart(cart(bank))
            if code == "sounds.name"]


def main():
    step = [[57, 0, 7]]
    bank = {"sfx": [{"name": "coin", "steps": step},
                    {"steps": step},
                    {"name": "", "steps": step},
                    {"name": "naïve ☃", "steps": step}],
            "music": [{"pattern": [0]}]}
    loaded = cart(bank).sounds
    expect("a loaded bank is the written bank", loaded, bank)
    expect("it survives a second trip",
           cart(json.loads(json.dumps(loaded))).sounds, bank)

    expect("name read", [mcart.sound_name(e) for e in bank["sfx"]],
           ["coin", None, "", "naïve ☃"])
    expect("24 characters kept",
           mcart.sound_name({"name": "a" * 24}), "a" * 24)
    expect("25 characters cut", mcart.sound_name({"name": "a" * 25}), "a" * 24)
    expect("not a string", mcart.sound_name({"name": 7}), None)
    expect("not an entry", mcart.sound_name(None), None)

    expect("valid names draw nothing", sound_findings(bank), [])
    expect("long name warns",
           sound_findings({"sfx": [{"name": "a" * 25, "steps": step}]}),
           [("warn", "sounds.name")])
    expect("24 characters draw nothing",
           sound_findings({"sfx": [{"name": "a" * 24, "steps": step}]}), [])
    expect("non-string name warns",
           sound_findings({"sfx": [{"name": 3, "steps": step}]}),
           [("warn", "sounds.name")])
    expect("no bank, no finding", sound_findings({}), [])

    with open(os.path.join(ROOT, "SPEC.md"), encoding="utf-8") as f:
        spec = f.read()
    said = re.search(r"`\"name\"`.*?at\s+most 24 characters", spec, re.S)
    if not said or mcart.SOUND_NAME_MAX != 24:
        FAIL.append("SPEC.md 8.1 does not say %d characters" % mcart.SOUND_NAME_MAX)

    for line in FAIL:
        print("sounds: " + line)
    if FAIL:
        return 1
    print("sounds: an sfx name is kept, read and checked as SPEC.md 8.1 says")
    return 0


if __name__ == "__main__":
    sys.exit(main())
