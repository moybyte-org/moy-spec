#!/usr/bin/env python3
"""The PICO-8 conformance corpus named by `p8_corpus.json`: where to download
each cart BY HAND, and which ones a directory already holds.

    python3 conformance/p8_corpus.py [--dir DIR] [--list]

THE CARTS ARE NOT REDISTRIBUTED, AND NOTHING HERE DOWNLOADS THEM. They are
their authors' work, several under licences that forbid redistribution, so
this repository holds LINKS (p8_corpus.json, which carries each cart's BBS
thread as well as its file). And the Lexaloffle BBS is for people: its terms
of use (https://www.lexaloffle.com/info.php?page=tos) ask that no script,
third-party client or crawler fetch from it without permission. So a person
opens each link in a browser and saves the file under the name the browser
gives it (`<lid>.p8.png`) into DIR -- by default ~/.cache/moy/p8, which is
where `make -C libmoy p8-carts` looks.

Without --list this prints which carts DIR holds and the links for the ones
it lacks. It exits 0 either way: the gate skips a cart that is not there.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS_JSON = os.path.join(HERE, "p8_corpus.json")
MIN_BYTES = 4000            # a saved BBS error page is far smaller than any cart


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
                    help="print every cart and its links, whatever DIR holds")
    args = ap.parse_args(argv[1:])
    carts = load()

    if args.list:
        for c in carts:
            print("%s\n    %s\n    cart:   %s\n    thread: %s\n"
                  % (c.get("title", c["lid"]), c["stresses"], c["cart"],
                     c.get("thread", "(not recorded)")))
        return 0

    missing = []
    for c in carts:
        path = os.path.join(args.dir, c["lid"] + ".p8.png")
        if os.path.exists(path) and os.path.getsize(path) >= MIN_BYTES:
            print("  have     %s" % c["lid"])
        else:
            print("  MISSING  %s" % c["lid"])
            missing.append(c)

    print("\n%d of %d carts in %s" % (len(carts) - len(missing), len(carts),
                                      args.dir))
    if missing:
        print("\nDownload these by hand, in a browser, saving each as the name"
              " shown:\n")
        for c in missing:
            print("  %s.p8.png  (%s)\n    cart:   %s\n    thread: %s\n"
                  % (c["lid"], c.get("title", c["lid"]), c["cart"],
                     c.get("thread", "(not recorded)")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
