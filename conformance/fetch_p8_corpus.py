#!/usr/bin/env python3
"""Fetch the PICO-8 conformance corpus named by `p8_corpus.json`.

    python3 conformance/fetch_p8_corpus.py [--dir DIR] [--list]

THE CARTS ARE NOT REDISTRIBUTED. They are their authors' work, several under
licences that forbid it, so this repository holds LINKS (p8_corpus.json, which
carries each cart's BBS thread as well as its file) and this downloads them to
a cache OUTSIDE the tree. `--list` prints the links and fetches nothing.

Be kind to the BBS: a cart already present and plausibly sized is not
re-fetched, and CI caches the directory so a green run costs zero requests.
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS_JSON = os.path.join(HERE, "p8_corpus.json")
MIN_BYTES = 4000            # a BBS error page is far smaller than any cart


def load():
    with open(CORPUS_JSON, encoding="utf-8") as fh:
        return json.load(fh)["carts"]


def default_dir():
    return (os.environ.get("MOY_P8_CORPUS")
            or os.path.join(os.path.expanduser("~"), ".cache", "moy", "p8"))


def main(argv):
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=default_dir())
    ap.add_argument("--list", action="store_true",
                    help="print the corpus and its links; download nothing")
    args = ap.parse_args(argv[1:])
    carts = load()

    if args.list:
        for c in carts:
            print("%s\n    %s\n    cart:   %s\n    thread: %s\n"
                  % (c.get("title", c["lid"]), c["stresses"], c["cart"],
                     c.get("thread", "(not recorded)")))
        return 0

    os.makedirs(args.dir, exist_ok=True)
    missing = 0
    for c in carts:
        dest = os.path.join(args.dir, c["lid"] + ".p8.png")
        if os.path.exists(dest) and os.path.getsize(dest) >= MIN_BYTES:
            print("  have %s" % c["lid"])
            continue
        subprocess.run(["curl", "-sS", "--fail", "--max-time", "60",
                        c["cart"], "-o", dest])
        size = os.path.getsize(dest) if os.path.exists(dest) else 0
        if size < MIN_BYTES:
            if os.path.exists(dest):
                os.remove(dest)
            print("  MISSING %s -- %s" % (c["lid"], c["cart"]))
            missing += 1
        else:
            print("  got  %s (%d bytes)" % (c["lid"], size))

    print("\ncorpus at %s" % args.dir)
    if missing:
        print("%d cart(s) could not be fetched; the gate will skip those."
              % missing)
    return 0        # never fail a build over someone else's hosting


if __name__ == "__main__":
    sys.exit(main(sys.argv))
