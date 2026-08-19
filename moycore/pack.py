"""The single-file cart -- a PROPOSAL, not part of core 0.2.

SPEC.md 3 says a cart is a folder and that how it travels is packaging the spec
deliberately says nothing about. That is right for AUTHORING: text files in a
folder mean your editor, your art tools and git already work, and a sprite edit
is a readable diff.

It is not enough for SHIPPING. There is nothing to drag into a chat, attach to
an itch.io page, hand a friend, or list in a catalogue -- and every small
console that got adoption had exactly that (PICO-8's .p8.png, TIC-80's .tic,
Playdate's .pdx). This module is the shipping form: the same folder, packed
into one deterministic file.

See proposals/single-file-cart.md for the format and the open naming question.

TWO PROPERTIES THAT MATTER, and both come from determinism:

  * The same folder always packs to the same bytes. No timestamps, no
    filesystem ordering, no compression-level drift. So a rebuild is a no-op in
    git and a mirror can dedup.
  * A cart has a stable ID -- `content_id`, a hash of the CONTENTS rather than
    of the container. It is computable from an unpacked folder too, so the id
    survives repacking and does not change if this format ever does.
"""

import hashlib
import zipfile

EXT = ".moyc"
_FIXED_DATE = (1980, 1, 1, 0, 0, 0)     # zip epoch: the only fully portable stamp

# Canonical order. The manifest first so a reader can refuse a cart without
# inflating its assets; then required, then optional, then anything else the
# author shipped (sorted, so the order never depends on a filesystem).
_ORDER = ("manifest.json", "main.lua", "sprites.moygfx", "map.moymap",
          "sounds.json", "config.json")


def canonical_order(names):
    known = [n for n in _ORDER if n in names]
    rest = sorted(n for n in names if n not in _ORDER)
    return known + rest


def content_id(files):
    """A stable cart id: sha256 over each (name, sha256(bytes)) in canonical
    order.

    Deliberately NOT the hash of the packed file. A cart's identity is its
    contents -- so the id is the same whether you have the folder or the
    package, and it survives a change to this container format. That is what
    makes it usable as a catalogue key."""
    h = hashlib.sha256()
    for name in canonical_order(files.keys()):
        blob = files[name]
        if not isinstance(blob, (bytes, bytearray)):
            blob = blob.encode("utf-8")
        h.update(name.encode("utf-8"))
        h.update(b"\0")
        h.update(hashlib.sha256(blob).digest())
    return h.hexdigest()


def pack_bytes(files):
    """{name: bytes} -> the packed cart, byte-for-byte reproducible."""
    import io
    buf = io.BytesIO()
    zf = zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9)
    try:
        for name in canonical_order(files.keys()):
            blob = files[name]
            if not isinstance(blob, (bytes, bytearray)):
                blob = blob.encode("utf-8")
            info = zipfile.ZipInfo(name, date_time=_FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16      # no host-dependent mode bits
            info.create_system = 3                # always "unix", never "whatever built it"
            zf.writestr(info, bytes(blob))
    finally:
        zf.close()
    return buf.getvalue()


def unpack_bytes(blob):
    """The packed cart -> {name: bytes}.

    Refuses any entry with a path separator. A cart is a FLAT folder (SPEC.md 3
    lists six files and no directories), so a nested path is either a mistake or
    a zip-slip attempt, and neither should be quietly flattened."""
    import io
    files = {}
    zf = zipfile.ZipFile(io.BytesIO(blob), "r")
    try:
        for info in zf.infolist():
            name = info.filename
            if name.endswith("/"):
                continue
            if "/" in name or "\\" in name or name.startswith(".."):
                raise ValueError("packed cart contains a path, not a plain file: %r" % name)
            files[name] = zf.read(info)
    finally:
        zf.close()
    return files


def read_pack(path):
    f = open(path, "rb")
    try:
        return unpack_bytes(f.read())
    finally:
        f.close()


def read_folder(path):
    """{name: bytes} for a .moy folder -- the same shape pack/unpack speak, so
    every consumer (loader, check, content_id) works on either form."""
    import os
    files = {}
    for entry in sorted(os.listdir(path)):
        full = os.path.join(path, entry)
        if os.path.isfile(full):
            f = open(full, "rb")
            try:
                files[entry] = f.read()
            finally:
                f.close()
    return files


def write_folder(path, files):
    import os
    if not os.path.isdir(path):
        os.makedirs(path)
    for name in canonical_order(files.keys()):
        blob = files[name]
        if not isinstance(blob, (bytes, bytearray)):
            blob = blob.encode("utf-8")
        f = open(os.path.join(path, name), "wb")
        try:
            f.write(bytes(blob))
        finally:
            f.close()
