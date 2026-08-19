# Proposal: sideload — how a cart gets onto a console

**Status: draft. Not part of core 0.2.** SPEC.md 3 deliberately says nothing
about how a cart travels; this stays true. What this proposes is not a
transport requirement but a **ladder of conventions**, with the floor at zero
code, so "works with `moy push`" is a claim the smallest OS can make honestly.
The design pressure it answers: a WiFi/HTTP requirement would exclude exactly
the minimal implementations the spec courts, and a device database inside the
tool rots and gates vendors on someone merging registry PRs. So the console
describes itself, and the baseline is the thing every console already has:
**carts are files on storage.**

## Tier 0 — file drop (the baseline; costs a text file)

A console conforms to tier 0 when:

1. Its carts live as SPEC.md 3 folders in a directory on storage a user can
   reach — an SD card, or the device itself exposed as a USB drive.
2. The root of that storage carries a marker, **`moy-console.json`**:

```json
{
  "moy_console": "0.1",
  "name": "moybyte T-Deck",
  "cart_root": "carts",
  "rescan": "boot"
}
```

`rescan` is `"boot"` (the console notices new carts on next boot — always
acceptable) or `"watch"` (it notices while running). Nothing else is required.
A vendor "implements" tier 0 by shipping this file on the SD card and
documenting which slot it lives in.

`moy push game.moy` at tier 0 is: find mounted volumes bearing the marker,
copy the folder into `cart_root`, done.

**USB mass storage is tier 0's best delivery.** Chips with a USB device
controller (ESP32-S2/S3/P4) can expose the cart storage as a drive via a USB
MSC class — the console then *is* the card reader. The one real constraint is
the two-writers problem: MSC hands the host a raw block device, so the console
must not touch that filesystem while the host has it mounted. The correct
shape is an explicit **disk mode** (what Playdate calls Data Disk): the
console pauses, shows a "connected" screen, serves MSC, and on eject/unplug
remounts and rescans. A mode switch, never concurrency. Chips without a USB
device controller (original ESP32, C3, C6) skip this and tier 0 means the SD
card travels. The reference implementation of disk mode belongs in libmoy's
ESP-IDF example — in the example's dependencies, never the library's, which
requires nothing.

## Tier 1 — serial (~100 lines, no network stack)

For consoles with a bidirectional USB/UART console. Line-oriented, over
whatever serial the device already has:

```
moy?                          -> one line: "moy-info " + the descriptor JSON
moy-put <path> <bytes>        -> "moy-ok"; the sender streams base64 in
                                 <= 512-byte lines and ends with "."; the
                                 receiver writes the file and replies
                                 "moy-ok" again, or "moy-err <reason>"
moy-del <path>                -> "moy-ok" / "moy-err <reason>"
moy-rescan                    -> "moy-ok"
moy-run <title>               -> "moy-ok" / "moy-err <reason>"; optional
```

Paths are relative to `cart_root` and must not escape it. Everything else the
console prints on serial is noise the tool ignores; replies are prefixed
`moy-` so the two interleave safely with logging. The tool probes only
USB-backed serial ports (a console on a bare UART is reachable with an
explicit `--to <port>`), and probing is one `moy?\n` line -- inert to any
firmware that does not speak this.

## Tier 2 — network (optional; the convenience tier)

For consoles that already carry a network stack. mDNS service
`_moy-console._tcp`, and over HTTP:

```
GET  /moy/info          -> the descriptor JSON
POST /moy/carts/<name>  -> cart upload (zip of the folder, or the
                           single-file form of proposals/single-file-cart.md)
POST /moy/rescan
POST /moy/run           -> {"title": ...}, optional
```

Nobody is asked to add WiFi for this tier; its real payoff is users (a phone
can push a cart), not conformance.

## The descriptor

One JSON object, shared by all tiers (tier 0 stores it as the marker file;
tiers 1–2 serve it):

```json
{
  "moy_console": "0.1",
  "name": "…",
  "transports": ["msc", "serial", "http"],
  "cart_root": "carts",
  "free_kb": 1932,
  "extensions": ["layers"]
}
```

`transports` lets `moy push` say what it found and pick the fastest;
`extensions` lets it warn before pushing a cart the console will refuse
(SPEC.md 10).

## The tool

`moy push game.moy` probes in order — mounted volumes with the marker, serial
ports answering `moy?`, mDNS — lists what it found, pushes to one. Where a
higher tier exists it may compose with tier 0: ask the console to enter disk
mode over serial/HTTP, then copy files. The tool never carries a device
database; a console that answers the probe is supported, including consoles
by vendors this repository has never heard of. That is the point.

This tool EXISTS: `moy.py push` (client code in `sideload.py`, and included
in the released `moy` binaries). All three probes and all three transports
are implemented and tested against mocks — `--list` shows what a probe finds,
`--to <dir|port|url>` skips probing, and a push to a marker-less directory
works with a warning, so an SD card is a valid target today. What does not
exist yet is any firmware that answers: until a console ships the marker file
or the protocol, `push` fails honestly, printing exactly where it looked.

## Status of implementations

| | tier 0 | tier 1 | tier 2 |
|---|---|---|---|
| `moy push` (this repo) | done | sender done (needs pyserial; bundled in releases) | client + mDNS done |
| moybyte P4 | SD (marker pending) | dev-serial exists, protocol pending | webserver exists, endpoints pending |
| moybyte T-Deck | SD (marker pending) | RX untested (listener never ported) | same as P4 |
| libmoy example | disk mode planned (S3-class, TinyUSB; builds in CI, proven on hardware with native USB) | — | — |
