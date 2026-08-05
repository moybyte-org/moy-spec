"""sideload -- the tool side of proposals/sideload.md.

`moy.py push` copies a cart onto a connected console. This module is the
finding and the copying: probe mounted volumes for the `moy-console.json`
marker (tier 0), serial ports that answer `moy?` (tier 1), and mDNS
`_moy-console._tcp` (tier 2), then push over whichever answered.

There is no device database here, on purpose. A console that describes itself
per the proposal is supported, including consoles by vendors this repository
has never heard of. When nothing answers -- which today is every device, the
firmware side is not implemented yet -- push fails with the map of where it
looked, so "why did nothing happen" is never the question.

Stdlib only, like the rest of the CLI. The one exception is tier-1 serial,
which needs pyserial (`pip install pyserial`); without it the serial probe is
reported as skipped rather than silently absent.
"""

import base64
import json
import os
import shutil
import socket
import struct
import sys
import time

MARKER = "moy-console.json"
MDNS_SERVICE = "_moy-console._tcp.local"
SERIAL_BAUD = 115200
DEFAULT_CART_ROOT = "carts"

# Never part of the pushed cart -- same exclusions as `run` and `pack`.
SKIP_FILES = ("moy-api.lua",)
SKIP_DIRS = ("thumbs", "__pycache__", ".git")


class SideloadError(Exception):
    """A push that cannot proceed; the message is for the user."""


class Console(object):
    """One found console: where it is and what it said about itself."""

    def __init__(self, kind, where, desc):
        self.kind = kind        # "volume" | "serial" | "http"
        self.where = where      # mountpoint | port device | base URL
        self.desc = desc or {}

    def __str__(self):
        name = self.desc.get("name", "unnamed console")
        return "%-6s %s  (%s)" % (self.kind, self.where, name)


def cart_files(src):
    """{relpath: bytes} for the cart folder, exclusions applied. Relpaths use
    forward slashes -- they cross OS boundaries by definition here."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in sorted(filenames):
            if fn in SKIP_FILES:
                continue
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, src).replace(os.sep, "/")
            with open(p, "rb") as f:
                out[rel] = f.read()
    return out


# --- tier 0: volumes ---------------------------------------------------------

_PSEUDO_FS = frozenset((
    "proc", "sysfs", "devtmpfs", "devpts", "tmpfs", "cgroup", "cgroup2",
    "securityfs", "pstore", "efivarfs", "bpf", "tracefs", "debugfs",
    "configfs", "fusectl", "mqueue", "hugetlbfs", "autofs", "binfmt_misc",
    "rpc_pipefs", "overlay", "squashfs", "nsfs", "ramfs", "fuse.gvfsd-fuse",
    "fuse.portal",
))


def _mounts():
    """Candidate volume roots, per platform."""
    if sys.platform == "win32":
        out = []
        for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
            root = letter + ":\\"
            try:
                if os.path.exists(root):
                    out.append(root)
            except OSError:
                pass
        return out
    if sys.platform == "darwin":
        base = "/Volumes"
        try:
            return [os.path.join(base, d) for d in sorted(os.listdir(base))]
        except OSError:
            return []
    # Linux and everything else with a /proc/mounts.
    out = []
    try:
        with open("/proc/mounts", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return out
    for line in lines:
        parts = line.split()
        if len(parts) < 3 or parts[2] in _PSEUDO_FS:
            continue
        # Mountpoints escape space/tab/newline/backslash as octal (\040 etc).
        mp = parts[1]
        for esc, ch in (("\\040", " "), ("\\011", "\t"),
                        ("\\012", "\n"), ("\\134", "\\")):
            mp = mp.replace(esc, ch)
        out.append(mp)
    return out


def read_marker(root):
    """The parsed marker at `root`, or None. Never raises -- an unreadable or
    non-JSON marker is simply not a console."""
    try:
        with open(os.path.join(root, MARKER), encoding="utf-8") as f:
            desc = json.load(f)
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    if not isinstance(desc, dict) or "moy_console" not in desc:
        return None
    return desc


def find_volumes():
    """(consoles, n_probed) -- every mounted volume bearing the marker."""
    found = []
    mounts = _mounts()
    for mp in mounts:
        desc = read_marker(mp)
        if desc is not None:
            found.append(Console("volume", mp, desc))
    return found, len(mounts)


def push_volume(console, src, log=print):
    """Tier 0: copy the cart folder into cart_root. Same-named cart replaced --
    that is what pushing the same game again means."""
    name = os.path.basename(src.rstrip("/\\"))
    root = os.path.join(console.where,
                        console.desc.get("cart_root", DEFAULT_CART_ROOT))
    os.makedirs(root, exist_ok=True)
    dst = os.path.join(root, name)
    if os.path.isdir(dst):
        log("  replacing %s" % dst)
        shutil.rmtree(dst)
    files = cart_files(src)
    for rel in sorted(files):
        p = os.path.join(dst, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(files[rel])
    log("pushed %s -> %s  (%d files)" % (name, dst, len(files)))
    if console.desc.get("rescan", "boot") == "boot":
        log("  this console rescans on boot -- eject/reboot to see the cart")


# --- tier 1: serial ----------------------------------------------------------

def _serial_module():
    try:
        import serial                    # noqa: F401  pyserial
        import serial.tools.list_ports   # noqa: F401
        return serial
    except ImportError:
        return None


def _read_reply(port, deadline):
    """The next `moy-` line before the deadline, or None. Everything else the
    console prints is logging and is ignored, per the proposal."""
    while time.time() < deadline:
        line = port.readline()
        if not line:
            continue
        line = line.strip()
        if line.startswith(b"moy-"):
            return line.decode("utf-8", "replace")
    return None


def find_serial():
    """(consoles, note) -- serial ports that answer `moy?` with `moy-info`.
    note explains an empty result ("pyserial not installed", "no ports", ...)."""
    serial = _serial_module()
    if serial is None:
        return [], "skipped -- pyserial not installed (pip install pyserial)"
    from serial.tools import list_ports
    # Only USB-backed ports: a console speaking this protocol is USB CDC, and
    # the alternative is writing "moy?" into 32 legacy ttyS devices at a
    # second each -- and into whatever non-console hardware sits on them.
    # A console on a bare UART is what --to <port> is for.
    ports = [p for p in list_ports.comports() if p.vid is not None]
    if not ports:
        return [], "no USB serial ports"
    found = []
    for p in ports:
        try:
            with serial.Serial(p.device, SERIAL_BAUD,
                               timeout=0.2, write_timeout=1) as s:
                s.reset_input_buffer()
                s.write(b"moy?\n")
                reply = _read_reply(s, time.time() + 1.0)
        except (OSError, serial.SerialException):
            continue
        if reply and reply.startswith("moy-info "):
            try:
                desc = json.loads(reply[len("moy-info "):])
            except ValueError:
                continue
            found.append(Console("serial", p.device, desc))
    return found, "%d port%s probed, none answered moy?" % (
        len(ports), "" if len(ports) == 1 else "s")


def push_serial(device, src, log=print):
    """Tier 1: the line protocol. Each file: moy-put, wait moy-ok, stream
    base64 lines, `.`, wait moy-ok. Then moy-rescan."""
    serial = _serial_module()
    if serial is None:
        raise SideloadError(
            "serial push needs pyserial: pip install pyserial")
    name = os.path.basename(src.rstrip("/\\"))
    files = cart_files(src)
    with serial.Serial(device, SERIAL_BAUD, timeout=0.2, write_timeout=5) as s:
        def expect_ok(what, seconds=10.0):
            reply = _read_reply(s, time.time() + seconds)
            if reply is None:
                raise SideloadError("%s: no reply from the console" % what)
            if not reply.startswith("moy-ok"):
                raise SideloadError("%s: console said %r" % (what, reply))

        for rel in sorted(files):
            data = files[rel]
            path = "%s/%s" % (name, rel)
            s.write(("moy-put %s %d\n" % (path, len(data))).encode())
            expect_ok("moy-put %s" % path)
            b64 = base64.b64encode(data)
            # 378 raw bytes -> 504 base64 chars, inside the 512-byte line cap.
            for i in range(0, len(b64), 504):
                s.write(b64[i:i + 504] + b"\n")
            s.write(b".\n")
            expect_ok("writing %s" % path)
            log("  %s (%d bytes)" % (path, len(data)))
        s.write(b"moy-rescan\n")
        expect_ok("moy-rescan")
    log("pushed %s over %s  (%d files)" % (name, device, len(files)))


# --- tier 2: mDNS + HTTP -----------------------------------------------------

def _dns_name(name):
    out = b""
    for label in name.split("."):
        raw = label.encode("ascii")
        out += struct.pack("B", len(raw)) + raw
    return out + b"\0"


def mdns_query_packet():
    """A standard one-question mDNS query: PTR for the service, QU bit set so
    a responder may answer us unicast."""
    header = struct.pack(">HHHHHH", 0, 0, 1, 0, 0, 0)
    question = _dns_name(MDNS_SERVICE) + struct.pack(">HH", 12, 0x8001)
    return header + question


def _skip_name(buf, off):
    """Past a possibly-compressed DNS name; returns the new offset."""
    while off < len(buf):
        n = buf[off]
        if n == 0:
            return off + 1
        if n & 0xC0 == 0xC0:            # compression pointer: 2 bytes, done
            return off + 2
        off += 1 + n
    return off


def _read_name(buf, off, depth=0):
    """A DNS name (following compression pointers) as a dotted string."""
    labels = []
    while off < len(buf) and depth < 16:
        n = buf[off]
        if n == 0:
            break
        if n & 0xC0 == 0xC0:
            ptr = struct.unpack(">H", buf[off:off + 2])[0] & 0x3FFF
            return ".".join(labels + [_read_name(buf, ptr, depth + 1)])
        labels.append(buf[off + 1:off + 1 + n].decode("utf-8", "replace"))
        off += 1 + n
    return ".".join(labels)


def parse_mdns_response(buf):
    """(host, port) pairs from one mDNS response packet: SRV records under the
    service give target+port, A records resolve targets to addresses. Anything
    malformed is skipped, not fatal -- multicast is a noisy neighborhood."""
    try:
        _, _, qd, an, ns, ar = struct.unpack(">HHHHHH", buf[:12])
    except struct.error:
        return []
    off = 12
    for _ in range(qd):
        off = _skip_name(buf, off) + 4
    srv = []            # (target, port)
    a = {}              # name -> dotted IPv4
    for _ in range(an + ns + ar):
        if off >= len(buf):
            break
        name = _read_name(buf, off)
        off = _skip_name(buf, off)
        if off + 10 > len(buf):
            break
        rtype, _, _, rdlen = struct.unpack(">HHIH", buf[off:off + 10])
        off += 10
        rdata = buf[off:off + rdlen]
        if rtype == 33 and len(rdata) >= 6:                     # SRV
            port = struct.unpack(">H", rdata[4:6])[0]
            target = _read_name(buf, off + 6)
            if name.endswith(MDNS_SERVICE):
                srv.append((target, port))
        elif rtype == 1 and rdlen == 4:                         # A
            a[name] = ".".join(str(b) for b in rdata)
        off += rdlen
    return [(a.get(target, target), port) for target, port in srv]


def find_mdns(timeout=1.0):
    """(consoles, note) -- consoles answering the mDNS service query, each
    verified by fetching its descriptor over HTTP."""
    seen = set()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
        sock.settimeout(0.2)
        sock.sendto(mdns_query_packet(), ("224.0.0.251", 5353))
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                buf, _ = sock.recvfrom(4096)
            except socket.timeout:
                continue
            for host, port in parse_mdns_response(buf):
                seen.add((host, port))
        sock.close()
    except OSError:
        return [], "no network"
    found = []
    for host, port in sorted(seen):
        base = "http://%s:%d" % (host, port)
        try:
            found.append(Console("http", base, http_info(base)))
        except SideloadError:
            continue
    return found, "no _moy-console._tcp response in %.1fs" % timeout


def http_info(base):
    """GET /moy/info -> the descriptor."""
    import urllib.request
    try:
        with urllib.request.urlopen(base + "/moy/info", timeout=3) as r:
            return json.loads(r.read().decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise SideloadError("%s/moy/info: %s" % (base, exc))


def push_http(base, src, log=print):
    """Tier 2: POST the packed single-file cart, then rescan. The body is the
    proposals/single-file-cart.md form -- deterministic, and one request."""
    import urllib.request
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from moycore import pack as _pack
    name = os.path.basename(src.rstrip("/\\"))
    blob = _pack.pack_bytes(cart_files(src))
    req = urllib.request.Request(
        "%s/moy/carts/%s" % (base, name), data=blob, method="POST",
        headers={"Content-Type": "application/octet-stream"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
    except OSError as exc:
        raise SideloadError("upload failed: %s" % exc)
    try:
        rescan = urllib.request.Request("%s/moy/rescan" % base,
                                        data=b"", method="POST")
        with urllib.request.urlopen(rescan, timeout=5) as r:
            r.read()
    except OSError:
        log("  (rescan request failed -- the console may need a reboot)")
    log("pushed %s -> %s  (%d bytes)" % (name, base, len(blob)))


# --- putting it together -----------------------------------------------------

def probe():
    """(consoles, notes) -- every console that answered, and one line per
    probe explaining what was searched. The notes ARE the failure message:
    when the list is empty they say exactly where the tool looked."""
    consoles = []
    notes = []

    vols, n = find_volumes()
    consoles += vols
    notes.append("volumes: %d mounted, %s" % (
        n, "%d with a %s marker" % (len(vols), MARKER) if vols
        else "none with a %s marker" % MARKER))

    ser, note = find_serial()
    consoles += ser
    notes.append("serial:  %s" % ("%d console%s" % (
        len(ser), "" if len(ser) == 1 else "s") if ser else note))

    net, note = find_mdns()
    consoles += net
    notes.append("mDNS:    %s" % ("%d console%s" % (
        len(net), "" if len(net) == 1 else "s") if net else note))

    return consoles, notes


def target_console(to):
    """--to resolved into a Console without probing. A directory, a serial
    device, or an http(s) URL."""
    if to.startswith(("http://", "https://")):
        return Console("http", to.rstrip("/"), http_info(to.rstrip("/")))
    if os.path.isdir(to):
        desc = read_marker(to)
        if desc is None:
            # A volume without the marker is still a place carts can live --
            # every SD card today. Say so, and use the default layout.
            print("  note: %s has no %s -- assuming cart_root %r"
                  % (to, MARKER, DEFAULT_CART_ROOT))
            desc = {"moy_console": "0.1", "cart_root": DEFAULT_CART_ROOT}
        return Console("volume", to, desc)
    if to.startswith("COM") or to.startswith("/dev/") or to.startswith("\\\\.\\"):
        return Console("serial", to, {})
    raise SideloadError("--to %r is not a directory, serial port or URL" % to)


def push(console, src, log=print):
    if console.kind == "volume":
        push_volume(console, src, log)
    elif console.kind == "serial":
        push_serial(console.where, src, log)
    else:
        push_http(console.where, src, log)
