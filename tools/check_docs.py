#!/usr/bin/env python3
"""Assert the documents agree with the things that generate their facts.

    python3 tools/check_docs.py          # exit 0 if the docs are consistent

The palette and the font are data rather than prose because "conformance needs
exact values" (SPEC.md 2), and CI proves the C copy still matches by regenerating
it and diffing. This is the same idea one level up: a handful of facts in the
prose have a machine-readable owner, and nothing was checking that the prose still
agreed with the owner. It didn't. A review on 2026-08-07 found the suite's scene
count wrong in three READMEs, the player's size wrong in four, and libmoy's audio
documented as absent months after it shipped.

WHAT GOES IN A DOCUMENT AS AN EXACT NUMBER, and what does not -- the rule these
checks enforce:

  * Quote an exact number when it is MEANINGFUL to the reader and CHEAP to
    verify. "Ten scenes, eight of them counted" tells you the shape of the suite,
    and `golden/hashes.json` settles it in one line of code. Checked below.
  * Use a BAND when the exact figure tells the reader nothing they need. The web
    player being "under 350 KB" is the whole point; that it is 315,106 bytes
    today is not, and quoting it cost four edits the first time the page grew.
    Exact bundle sizes therefore live in `runner/VERSION` (written by the build)
    and nowhere else.
  * A number produced by running a program belongs to that program. Never paste
    its output into a README -- that is a screenshot, and it rots.

Checks, cheapest first. Each is here because its absence let a real error ship.
"""

import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def tracked(*patterns):
    out = subprocess.run(["git", "-C", ROOT, "ls-files"] + list(patterns),
                         capture_output=True, text=True).stdout.split()
    return [p for p in out if os.path.isfile(os.path.join(ROOT, p))]


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8", errors="replace") as f:
        return f.read()


PROBLEMS = []


def fail(rel, msg):
    PROBLEMS.append("%s: %s" % (rel, msg))


# --- 1. the suite's scene count ----------------------------------------------
#
# Owner: conformance/golden/hashes.json, the manifest build.py writes. Four
# documents quote this and three of them said "nine" after a tenth scene landed.

# "one" is deliberately absent: "one scene per area", "a provisional scene" and
# "one conformance scene" are rates and singulars, never a claim about how many
# the suite holds.
WORD = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
        "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12}


def check_scene_counts():
    manifest = json.loads(read("conformance/golden/hashes.json"))
    scenes = manifest["scenes"]
    total = len(scenes)
    core = sum(1 for s in scenes if s.get("core"))
    allowed = {total, core, total - core}

    # A numeral (digit or word) directly before "scene"/"scenes", optionally
    # with one qualifier between them ("8 core scenes", "ten provisional
    # scenes"). Anything else is prose the check does not reach.
    pat = re.compile(r"\b([0-9]{1,2}|%s)\s+(?:\w+\s+)?scenes?\b"
                     % "|".join(WORD), re.I)
    for rel in tracked("*.md"):
        for line in read(rel).splitlines():
            for m in pat.finditer(line):
                raw = m.group(1).lower()
                n = int(raw) if raw.isdigit() else WORD[raw]
                if n not in allowed:
                    fail(rel, "says %r, but the suite has %d scenes (%d core). "
                              "Allowed: %s. If the sentence is historical, write "
                              "it without a numeral."
                         % (m.group(0).strip(), total, core,
                            sorted(allowed)))


# --- 2. every SPEC.md cross-reference resolves -------------------------------
#
# Owner: SPEC.md's own headings. Nine source comments cite section NUMBERS
# (`moy.h` cites 12.1, both ports cite 12.2, moycore cites 12.1/12.2, the wasm
# proposal cites 12.6 three times), so renumbering a section silently breaks
# citations nobody will ever re-read. This makes that loud.

def spec_sections():
    ids = set()
    for line in read("SPEC.md").splitlines():
        m = re.match(r"^#{2,3}\s+(\d+(?:\.\d+)?)[.\s—-]", line)
        if m:
            ids.add(m.group(1))
    return ids


def check_spec_refs():
    ids = spec_sections()
    if not ids:
        fail("SPEC.md", "no numbered sections found -- the ref check is blind")
        return
    # Only forms that are unambiguously a reference: a section sign, or the
    # filename. This deliberately does not match bare decimals, so a measured
    # "12.35 M ops/s" is never mistaken for a citation.
    pat = re.compile(r"(?:§|SPEC\.md\s+§?)(\d+(?:\.\d+)?)")
    for rel in tracked("*.md", "*.py", "*.c", "*.h", "*.lua", "*.mjs",
                       "Makefile", "*/Makefile"):
        if rel.startswith("libmoy/vendor/"):
            continue
        for i, line in enumerate(read(rel).splitlines(), 1):
            for m in pat.finditer(line):
                if m.group(1) not in ids:
                    fail(rel, "line %d cites SPEC.md %s, which is not a section"
                         % (i, m.group(1)))


# --- 3. the control legend is quoted, not paraphrased ------------------------
#
# Owner: tools/release_readme.py. Four copies of this sentence produced three
# different wrong answers, all of them missing Space.

def check_controls():
    sys.path.insert(0, HERE)
    import release_readme

    # Whitespace-insensitive: README.md hard-wraps its prose, and where the
    # legend happens to break is not a fact anybody should have to preserve.
    def flat(s):
        return " ".join(s.split())

    if flat(release_readme.CONTROLS.rstrip(".")) not in flat(read("README.md")):
        fail("README.md", "does not quote the control legend verbatim. It is "
                          "owned by tools/release_readme.py (CONTROLS) because "
                          "the copies drifted; paste it, do not rephrase it.")


# --- 4. no document restates the player bundle's exact size ------------------
#
# Owner: runner/VERSION. A band is what a reader needs; the exact figure moved
# 19 KB in three commits and was stale in four documents at once.

def check_no_exact_bundle_size():
    version = json.loads(read("runner/VERSION"))
    sizes = {f["bytes"] for f in version.get("files", {}).values()}
    sizes.add(sum(f["bytes"] for f in version.get("files", {}).values()))
    forms = set()
    for n in sizes:
        forms.add(str(n))
        forms.add("{:,}".format(n))
    for rel in tracked("*.md", "*.html"):
        if rel.startswith("runner/"):
            continue          # BUILD.md is allowed to talk about the build
        text = read(rel)
        for form in sorted(forms):
            if form in text:
                fail(rel, "quotes %s, a live byte count from runner/VERSION. "
                          "Use a band (\"under 350 KB\") -- the exact figure "
                          "changes whenever the page does." % form)


# --- 5. a measurement is quoted in exactly one document ----------------------
#
# The bug that started all this: SPEC.md 6.1 retracted a per-pixel cost as a
# measurement artifact, RATIONALE.md went on asserting it, and both were right
# about their own copy. A figure restated in three documents gets corrected in
# one. Add a row here when a new measurement lands; the point is that the
# addition is what forces the choice of a home.

# Scope note: .md files only, which is where the drift happened. A figure
# repeated in a Makefile comment or a Kconfig help string is usually fine and
# sometimes required -- a build flag needs its reason where the flag is set, and
# somebody toggling a Kconfig option reads its cost right there. Those are second
# homes on purpose, not copies nobody meant to keep.

SINGLE_HOME = {
    "the all-PSRAM heap slowdown": r"(2×|2x|roughly 2) slower",
    "the narrow-span per-pixel cost": r"\d{2,3} ?ns/px",
    "libmoy's Lua flash cost": r"140 KB of flash",
    # SPEC.md 15 and proposals/wasm-runtime.md carried these three side by side,
    # with the "Lua does not compile into the fast tier" paragraph near-verbatim
    # in both. The proposal owns them; the spec states the one consequence that
    # reaches back into its own text and points at the rest.
    "the WASM interpreter ratio": r"1\.09\s?×",
    "the WASM AOT ratio": r"(16|16\.3)\s?×",
    "the straight-line arithmetic ratio": r"91\s?×",
}


def check_measurements_have_one_home():
    for what, pat in SINGLE_HOME.items():
        rx = re.compile(pat, re.I)
        holders = [rel for rel in tracked("*.md")
                   if rx.search(" ".join(read(rel).split()))]
        if len(holders) > 1:
            fail(", ".join(holders),
                 "all quote %s. A measurement belongs to one document; the "
                 "others cite it by name. (%s)" % (what, pat))


# --- 6. prose does not get duplicated across documents (a ratchet) -----------
#
# The check that found the rest. Two documents sharing a run of nine words is
# either a quotation or a paragraph somebody wrote twice, and the second kind is
# what goes stale in one copy. SPEC.md and RATIONALE.md shared 29 such runs
# before this existed -- the FPU sentence verbatim, the hex-nibble argument three
# times over, SPEC.md 15 restating measurements the wasm proposal already owned.
#
# The budget below is a CEILING, not a target: raising a number is a legitimate
# way to resolve a failure, but it should come with a reason in the commit, and
# "I quoted the spec on purpose" is a good one. Both surviving large pairs are
# exactly that -- libmoy/README.md and conformance/README.md open by quoting
# SPEC.md 1.1 and 11 respectively, attributed, which is the opposite of drift.

DUP_BUDGET = {
    ("SPEC.md", "libmoy/README.md"): 6,           # quotes 1.1 on the pixel format
    ("SPEC.md", "conformance/README.md"): 5,      # quotes 11 as its epigraph
    ("RATIONALE.md", "SPEC.md"): 4,               # topic sentences + one attributed rule
    ("SPEC.md", "proposals/wasm-runtime.md"): 1,  # 12.6's phrasing, deliberately
}
DUP_FLOOR = 3          # an unlisted pair may share this many runs incidentally
SHINGLE = 9


def check_prose_duplication():
    import collections
    docs = [f for f in tracked("*.md") if not f.endswith("THIRD_PARTY.md")]
    seen = collections.defaultdict(set)
    for rel in docs:
        text = re.sub(r"```.*?```", "", read(rel), flags=re.S)
        text = re.sub(r"[`*_#|>]", "", " ".join(text.split()))
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            words = [w.lower().strip(",;:()—-") for w in sentence.split()]
            if len(words) < SHINGLE:
                continue
            for i in range(len(words) - SHINGLE + 1):
                seen[" ".join(words[i:i + SHINGLE])].add(rel)
    counts = collections.Counter()
    for holders in seen.values():
        if len(holders) > 1:
            for pair in ((a, b) for i, a in enumerate(sorted(holders))
                         for b in sorted(holders)[i + 1:]):
                counts[pair] += 1
    for pair, n in counts.items():
        cap = DUP_BUDGET.get(pair, DUP_FLOOR)
        if n > cap:
            fail(" <-> ".join(pair),
                 "share %d runs of %d words (budget %d). Either one of them "
                 "should cite the other instead of restating it, or raise the "
                 "budget in DUP_BUDGET with a reason." % (n, SHINGLE, cap))


def main():
    check_scene_counts()
    check_spec_refs()
    check_controls()
    check_no_exact_bundle_size()
    check_measurements_have_one_home()
    check_prose_duplication()
    if PROBLEMS:
        print("check_docs: %d problem%s" % (len(PROBLEMS),
                                            "" if len(PROBLEMS) == 1 else "s"))
        for p in PROBLEMS:
            print("  " + p)
        return 1
    print("check_docs: the docs agree with what generates their facts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
