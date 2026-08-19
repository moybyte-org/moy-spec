# Proposal: a single-file shipping form for carts

**Status: proposal. Not part of core 0.2.** Implemented in `moycore/pack.py` and
`moy.py pack` / `moy.py unpack` so the idea can be used and argued with, but
SPEC.md is unchanged and this is not required of any host.

## The problem

SPEC.md 3 says a cart is a folder, and that how the folder travels is packaging
the spec deliberately says nothing about. That is right for **authoring**: text
files in a folder mean your editor, your art tools and git already work, and a
sprite edit shows up as a readable diff.

It is not enough for **shipping**. There is nothing to drag into a chat, attach
to an itch.io page, hand to a friend, put behind a URL, or list in a catalogue.
Every small console that got adoption had exactly that artifact:

| console | authoring form | shipping form |
|---|---|---|
| PICO-8 | `.p8` (text) | `.p8.png` |
| TIC-80 | project dir | `.tic` |
| Playdate | source tree | `.pdx` bundle |
| moy | `.moy/` folder | — |

The gap is not theoretical. A conformance suite that a host cannot *fetch*, a
registry that cannot key on anything, and a "try this cart" link that has to be
a zip someone assembled by hand are all the same missing artifact.

## The proposal

A packed cart is a **zip of the cart folder's files, flat, written
deterministically**. Nothing else. Reading it needs a zip decoder, which every
target platform already has or can carry in a few KB.

Extension: **`.moyc`** — see the open question below.

Determinism means, precisely:

- entries in canonical order: `manifest.json`, `main.lua`, `sprites.moygfx`,
  `map.moymap`, `sounds.json`, `config.json`, then anything else sorted;
- every timestamp `1980-01-01 00:00:00` (the zip epoch, the only fully portable
  stamp);
- mode bits fixed at `0644`, `create_system` always 3;
- deflate at a fixed level.

So the same folder always packs to the same bytes. A rebuild is a no-op in git,
a mirror can dedup, and two people who pack the same cart get the same file.

`manifest.json` comes first on purpose: a host can refuse a cart on its
`runtime` or `extensions` (SPEC.md 10, 15) without inflating its assets.

Nested paths are **refused** on read, not flattened. A cart is a flat folder —
SPEC.md 3 lists six files and no directories — so a path separator in an entry
name is either a mistake or a zip-slip attempt.

## Cart identity

A packed cart has a **content id**: sha256 over each `(name, sha256(bytes))` in
canonical order.

Deliberately *not* the hash of the packed file. A cart's identity is its
contents, so:

- the id is the same whether you have the folder or the package;
- it survives a repack, and it survives a change to this container format;
- `moy check` can print it for an unpacked folder, which is where authors live.

That is what makes it usable as a registry key. `moy.py pack` and `moy.py check`
both print it.

## What this does not do

- **No signing, no manifest of manifests, no delta updates.** Those are registry
  concerns and this is a file format. A registry can sign the id.
- **No compression tuning.** Carts are tens of KB; the sheet and map are hex
  text and deflate to nothing.
- **It does not replace the folder.** The folder stays the source of truth and
  the thing you edit. `pack` is a build step, `unpack` is a debugging step.

## Open question: the extension

`.moyc` is what the implementation uses, and it is the part most worth arguing
about, because it is the name people will type.

- **`.moyc`** — short, obviously related to `.moy`, no collision with the
  folder. Reads as "compiled", which is wrong; nothing is compiled.
- **`.moy` for both**, distinguished by whether it is a directory. Elegant, and
  `moycore.load_cart` already accepts either. But `pack mygame.moy` then has
  nowhere to write, and "is it a file or a folder" becomes a question every tool
  has to ask.
- **`.moycart`** — unambiguous, ugly, long.
- **`.p8.png`-style image container** — a playable cart that is *also* a
  screenshot is genuinely charming and is a large part of why PICO-8 carts
  spread on social media. It costs a PNG encoder on the writing side and a
  chunk parser on the reading side, and the label has to be generated. Worth
  considering as a *second* form later, not as the first one.

## Try it

```
python3 moy.py pack examples/brick_siege.moy      # -> brick_siege.moyc + its id
python3 moy.py unpack examples/brick_siege.moyc
python3 moy.py check examples/brick_siege.moyc    # check reads either form
```
