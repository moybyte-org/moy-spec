"""compiled -- making a compiled cart: `moy new --wasm`, `moy new --jet`, `moy build`.

A compiled cart (SPEC.md 16) is a folder like any other with a WebAssembly
module as its `main`, and its source in `src/`. This module is the loop around
that source:

  * `new_cart` scaffolds one from a starter in templates/: `wasm`, a C cart
    that fills a frame per pixel and draws over it with the verbs, or `jet`,
    JetExamples' template-cube drawn by Jet (CubeCoders' MIT rasteriser), whose
    sources it fetches at a pinned commit, each file checked by sha256.
  * `build` compiles every C and C++ file under `src/` into the manifest's
    `main`, with a pinned wasi-sdk fetched by sha256 the first time, and holds
    the result to SPEC.md 16 with the same checks `moy check` runs.
  * `Watcher` rebuilds when a file under `src/` changes, which is how `moy
    play` and `moy web` reload a compiled cart as you save.

THE FLAGS, each for a reason the reference console measured (moybyte#158):

  * `-mnontrapping-fptoint`: a C cast from float to int is undefined out of
    range, which wasm's saturating conversion honours in one instruction;
    without it clang emits a range guard around a trapping one, and an ahead-
    of-time compiler adds its own checks behind that.
  * the two inline thresholds at 300: a rasteriser's per-pixel calls sit in
    blocks clang's estimate calls cold, and stayed calls -- one per pixel.
  * no WASI: wasi-libc and libc++ are linked statically for the containers,
    strings and maths, and `src/runtime.c` answers the handful of calls they
    make to an operating system, so the module imports only from "moy". The
    build refuses a module that imports anything else, naming the import.
  * the memory is the manifest's, minimum and maximum, laid out stack first
    (an overflow leaves linear memory and traps rather than running into the
    data), then the static data, then the heap to the end.
  * `__stack_pointer` is exported, for `par` (SPEC.md 16.10).
  * paths are mapped out of the binary, so the module does not depend on where
    the cart was built.

Stdlib only, like the rest of the CLI.
"""

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
TEMPLATES = os.path.join(HERE, "templates")
CART_HEADER = os.path.join(HERE, "libmoy", "include", "moy_cart.h")

PAGE = 65536
DEFAULT_STACK = 64 * 1024

# wasi-sdk 24: clang 18, wasi-libc and libc++. One release for every platform
# the CLI ships on, each archive pinned by sha256; $WASI_SDK_PATH points at
# another install instead, and the build says so.
WASI_SDK_VERSION = "24.0"
WASI_SDK_URL = ("https://github.com/WebAssembly/wasi-sdk/releases/download/"
                "wasi-sdk-24/wasi-sdk-24.0-%s.tar.gz")
WASI_SDK = {
    ("Linux", "x86_64"): ("x86_64-linux", 118879731,
                          "c6c38aab56e5de88adf6c1ebc9c3ae8da72f88ec2b656fb024eda8d4167a0bc5"),
    ("Linux", "arm64"): ("arm64-linux", 119660865,
                         "ae6c1417ea161e54bc54c0a168976af57a0c6e53078857886057a71a0d928646"),
    ("Darwin", "x86_64"): ("x86_64-macos", 109975956,
                           "4bfc274ae8b68c771dd93e32ad4bd695336ca46b585beb3b1260e5602dbc11a2"),
    ("Darwin", "arm64"): ("arm64-macos", 108199177,
                          "aeae999396d5f5caa5ce419f52e83c35869d5fd21d40af80acba2c80f51b0b3a"),
    ("Windows", "x86_64"): ("x86_64-windows", 495098073,
                            "0f934c6e7e171b5627c81b697a9e57e96d65cd889f56ce6077350de48978afd3"),
}

COMMON_FLAGS = ["--target=wasm32-wasi", "-O2", "-mnontrapping-fptoint",
                "-mllvm", "-inline-threshold=300",
                "-mllvm", "-inline-cold-callsite-threshold=300",
                "-Wall"]
C_FLAGS = ["-std=c11"]
CXX_FLAGS = ["-std=c++17", "-fno-exceptions", "-fno-rtti", "-fno-threadsafe-statics"]
C_EXT = (".c",)
CXX_EXT = (".cpp", ".cc", ".cxx")
HEADER_EXT = (".h", ".hpp", ".hh", ".hxx", ".inc")

# Jet at the commit JetExamples 57b05a2 pins as its components/Jet submodule,
# the one the template-cube example was written and measured against: the
# files the starter compiles and the headers they include, and the licence.
JET_REPO = "CubeCoders/Jet"
JET_COMMIT = "19018b52c04d92c615d1ade2db5eb7198c7af21c"
JET_RAW = "https://raw.githubusercontent.com/%s/%s/%%s" % (JET_REPO, JET_COMMIT)
# Every file Jet's carts compile (the same set the reference console's Jet
# carts vendor), so a starter can turn lighting or textures on and still build.
JET_FILES = {
    "LICENSE":
        "e1b2f37275330b67e3b2354554265691c914d032fbff90b5cc7189313e97249f",
    "src/BlendSpans.cpp":
        "4a53950e195c2cca2e472917ad4861661667a09e1484ebde2291e44729e503ff",
    "src/BlendSpans.hpp":
        "a4c429db186f6348560700ca279beda0ed234c9768e0feb4d16d7ce71012d859",
    "src/Camera.cpp":
        "9dbb0a6a2e9996cd88dfd84fa2ef72f5d567630a7da68b4df23aa89f0db6ba5f",
    "src/Camera.hpp":
        "d57ce190b41a55e0f08e6310947ccaa6c0dc97ea071e0ef62be7a97ec7455e2b",
    "src/DepthBuckets.hpp":
        "21b02a20a600e6f457d4836a104685dbdf14edcbc4784f895c0ed4c76b0b4fb9",
    "src/EnvironmentMapping.hpp":
        "d8e8b1f9ef4b120284e643ac4884fa6ba61a815ed98cd74617e8b82b6ed68a1d",
    "src/FastMath.hpp":
        "0814e71248d9ac3affbf23de10dbada623721b53e6c2192b3edcb4adb6442205",
    "src/Light.cpp":
        "00eaf8871699d7f6a8086e4015f8d12bb700a9bfb82ef8aa4615a3276e0fd2d7",
    "src/Light.hpp":
        "7e1fc421971224326c069479c7c764646e866e539c722077fd12088601a64f7e",
    "src/Material.cpp":
        "292ef0175624b07dceb9d0928bab7deb6cb33e47e02b5065f735c04e2d5201a0",
    "src/Material.hpp":
        "7ffdb459368c7cf90f33ba6355f9c9d146fadbaf5aa49c5fb6a45e8467494941",
    "src/Math.hpp":
        "ad5b07e2342976b7b2dd7508100848a002963fdde49c566332f8636dca27115d",
    "src/ObjLoader.h":
        "dd84e49ebc3ab3188ea2048880329fdfdb0332afade6fadb526a8ed3a06dda89",
    "src/Object.cpp":
        "35482065eb3475b906330f2e2629f849c79b536170b61842b9d4c1843cd489a9",
    "src/Object.hpp":
        "63e9ea17bc8855287841a673d337017023fdd9768e040ee78ddb0e695af2cbd3",
    "src/ParticleSystem.hpp":
        "7c23f2e4589176df1eb3923c55cc8e0b7623341c9c3b2d8f898624d823eaf456",
    "src/Picking.hpp":
        "4e491eda389edcaab8a15673d10d898dcc275504d049cc31717071cc290f426d",
    "src/PostFX.cpp":
        "820b13f1a2a022d7d118f5e8e4ee95d84be52fa9deb84e78f9fdfda70be9a5a4",
    "src/PostFX.hpp":
        "c194e3cb07097c0510959c3d78c69f8cb5915687341576ec72867397630f2eef",
    "src/Primitives.cpp":
        "a335888f23691a31ecc2c30f294270f04656383300ec5693b7fe9f587c688575",
    "src/Primitives.hpp":
        "e41af4a999306581eb5e19ae6584c7149b1410fd9ca0734446be24d389b3ad8a",
    "src/Renderer.cpp":
        "22d6577052d9493eab606af217f789560618e5df918ff43d551ad5b5df90ac5e",
    "src/Renderer.hpp":
        "e0d81d11b374fccf88dc0fc07195d204ba07688b2ff3fe746090897fe824386d",
    "src/Scene.cpp":
        "41708d19373e4dae6e47fde4afc843f138269fa9f4a7eff17fa1da16336cf1d7",
    "src/Scene.hpp":
        "040b24b2f9cbf6a8d80b63c20e5d38f00e432ba1925dcde572fb9c892e639035",
    "src/Shader.hpp":
        "96344d2fbe2d4d0bebc18d9d3a3b8de51c91f85c6598e35156bd1ff52b6d4c19",
    "src/Specular.hpp":
        "f590dba0c22ce62a8ac5e99b7f647c83ca23378c2b199518b5479d01f858f210",
    "src/Sprite2D.cpp":
        "64b987a3c914520e1b8c51f55d5a2e7842fd1d4a21d2d58a76d18b0af2c7051f",
    "src/Sprite2D.hpp":
        "daacbc99217e22bd83619cc9b02b663aeb8636c2619ad908274d19f64ca41cf1",
    "src/Texture.cpp":
        "cead65577eaa2a5eede41736b66e35476eea6ce57ab9ac8bb7d01a16f234c949",
    "src/Texture.hpp":
        "4c2d8a4b95cb10069045322d31144b88c0c5e124ce69338074d946c4189c5f49",
    "src/TextureSpans.hpp":
        "0134c2d28b7f82b81f4b6a9f89cfae6f2e6194dc84ff72f3eb9d3ec7c6ea3cb5",
    "src/TriangleSpans.hpp":
        "927631789b3595705079df2c861d18b3763c251a78e940aac945d7d63232da74",
    "src/TrigLUT.cpp":
        "678df2a0d4e08f5d63580e17f0f97c53fc6770a82e17b1ae934a0be1d5c2fc25",
    "src/TrigLUT.hpp":
        "9762626b5badf2be3176a43907ea535de0eb1359def37cd49e121806ff88cf77",
}

# The starters' manifests. fps "free": both scale their motion by dt.
MANIFESTS = {
    "wasm": {"format": "moy-1", "title": None, "version": 1, "runtime": "wasm",
             "main": "main.wasm", "memory": 4, "fps": 60, "input": ["buttons"],
             "writable": ["saves/"]},
    "jet": {"format": "moy-1", "title": None, "version": 1, "runtime": "wasm",
            "main": "main.wasm", "memory": 8, "fps": "free", "input": ["buttons"]},
}


class BuildError(Exception):
    """A build that cannot finish; the message is for the person building."""


def say(msg):
    """Print now: a rebuild runs beside the player, whose own output would
    otherwise overtake a buffered line."""
    print(msg, flush=True)


# -- the toolchain ----------------------------------------------------------------


def data_dir():
    """Where moy keeps what it downloads: a per-user data directory."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    return os.path.join(base, "moy")


def _exe(name):
    return name + ".exe" if sys.platform == "win32" else name


def _is_sdk(path):
    return bool(path) and os.path.isfile(os.path.join(path, "bin", _exe("clang")))


def platform_key():
    machine = platform.machine().lower()
    arch = {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "arm64",
            "aarch64": "arm64"}.get(machine, machine)
    return platform.system(), arch


def sdk_home():
    return os.path.join(data_dir(), "toolchain", "wasi-sdk-" + WASI_SDK_VERSION)


def find_sdk():
    """(path, how) of a wasi-sdk to build with, or (None, why not)."""
    env = os.environ.get("WASI_SDK_PATH")
    if env:
        if _is_sdk(env):
            return env, "$WASI_SDK_PATH"
        return None, "$WASI_SDK_PATH is %s, which has no bin/%s" % (env, _exe("clang"))
    if _is_sdk(sdk_home()):
        return sdk_home(), "pinned"
    return None, "not fetched yet"


def fetch_sdk(log=say):
    """The pinned wasi-sdk for this machine, downloaded and checked by sha256
    into the data directory when absent. Returns its path."""
    found, _how = find_sdk()
    if found:
        return found
    key = platform_key()
    if key not in WASI_SDK:
        raise BuildError("no pinned wasi-sdk for %s %s; install wasi-sdk %s and set "
                         "$WASI_SDK_PATH" % (key[0], key[1], WASI_SDK_VERSION))
    name, size, digest = WASI_SDK[key]
    url = WASI_SDK_URL % name
    home = sdk_home()
    os.makedirs(os.path.dirname(home), exist_ok=True)
    log("moy: fetching wasi-sdk %s for %s (%d MB, once)"
        % (WASI_SDK_VERSION, name, size // (1 << 20)))
    fd, part = tempfile.mkstemp(prefix="wasi-sdk-", suffix=".part",
                                dir=os.path.dirname(home))
    h = hashlib.sha256()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "moy-cli"})
        with os.fdopen(fd, "wb") as out, urllib.request.urlopen(req, timeout=600) as r:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                h.update(chunk)
                out.write(chunk)
        if h.hexdigest() != digest:
            raise BuildError("%s hashes to %s; the pin is %s -- refused"
                             % (url, h.hexdigest(), digest))
        tmp = tempfile.mkdtemp(prefix="wasi-sdk-", dir=os.path.dirname(home))
        try:
            with tarfile.open(part, "r:gz") as tar:
                top = tar.getmembers()[0].name.split("/")[0]
                if hasattr(tarfile, "data_filter"):
                    tar.extractall(tmp, filter="data")
                else:
                    tar.extractall(tmp)
            if not os.path.isdir(home):
                os.replace(os.path.join(tmp, top), home)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    except OSError as exc:
        raise BuildError("could not fetch %s: %s" % (url, exc))
    finally:
        if os.path.exists(part):
            os.remove(part)
    if not _is_sdk(home):
        raise BuildError("%s unpacked without bin/%s" % (url, _exe("clang")))
    log("moy: wasi-sdk %s is in %s" % (WASI_SDK_VERSION, home))
    return home


# -- the cart ---------------------------------------------------------------------


def manifest(cart):
    path = os.path.join(cart, "manifest.json")
    try:
        with open(path, encoding="utf-8") as f:
            man = json.load(f)
    except (OSError, ValueError) as exc:
        raise BuildError("no readable manifest.json in %s: %s" % (cart, exc))
    if not isinstance(man, dict):
        raise BuildError("manifest.json is not a JSON object")
    return man


def is_compiled(cart):
    try:
        return manifest(cart).get("runtime") == "wasm"
    except BuildError:
        return False


def has_source(cart):
    return bool(_sources(cart))


def _walk(top):
    out = []
    for dirpath, dirnames, filenames in os.walk(top):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        out += [os.path.join(dirpath, f) for f in sorted(filenames)]
    return out


def _sources(cart):
    src = os.path.join(cart, "src")
    if not os.path.isdir(src):
        return []
    return [p for p in _walk(src) if p.endswith(C_EXT + CXX_EXT)]


def _include_dirs(cart):
    """src/ and every folder under it that holds a header, src/ first."""
    src = os.path.join(cart, "src")
    dirs = [src]
    for p in _walk(src):
        d = os.path.dirname(p)
        if p.endswith(HEADER_EXT) and d not in dirs:
            dirs.append(d)
    return dirs


def source_stamp(cart):
    """What a rebuild depends on that `moy play` can watch: every file under
    src/ and the manifest, by path, size and mtime."""
    h = hashlib.sha1()
    for p in _walk(os.path.join(cart, "src")) + [os.path.join(cart, "manifest.json")]:
        try:
            st = os.stat(p)
        except OSError:
            continue
        h.update(("%s|%d|%d\n" % (p, st.st_size, st.st_mtime_ns)).encode())
    return h.hexdigest()


def needs_build(cart):
    """True when the module is missing or older than a file it is built from."""
    try:
        main = os.path.join(cart, manifest(cart).get("main") or "main.wasm")
    except BuildError:
        return False
    if not has_source(cart):
        return False
    if not os.path.isfile(main):
        return True
    built = os.stat(main).st_mtime_ns
    for p in _walk(os.path.join(cart, "src")) + [os.path.join(cart, "manifest.json")]:
        if os.stat(p).st_mtime_ns > built:
            return True
    return False


def _cache_dir(cart):
    key = hashlib.sha1(os.path.abspath(cart).encode()).hexdigest()[:16]
    return os.path.join(data_dir(), "build", key)


def _deps_newer(dep_file, than):
    """True when any file the depfile lists is newer than `than` (ns), or the
    depfile cannot be read."""
    try:
        with open(dep_file, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return True
    text = text.replace("\\\n", " ")
    _target, _, deps = text.partition(": ")
    for dep in re.split(r"(?<!\\)\s+", deps.strip()):
        dep = dep.replace("\\ ", " ")
        if not dep:
            continue
        try:
            if os.stat(dep).st_mtime_ns > than:
                return True
        except OSError:
            return True
    return False


def _library(cart, path):
    """True when `path` sits in a folder under src/ that carries its own
    LICENSE: somebody else's library, compiled without warnings, which are
    its authors' to read rather than the cart's."""
    src = os.path.join(cart, "src")
    d = os.path.dirname(path)
    while len(d) > len(src) and d.startswith(src):
        if any(os.path.isfile(os.path.join(d, n)) for n in ("LICENSE", "LICENSE.txt")):
            return True
        d = os.path.dirname(d)
    return False


def _shown(path):
    rel = os.path.relpath(path)
    return path if rel.startswith("..") else rel


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def build(cart, stack=DEFAULT_STACK, log=say, sdk=None, jobs=None):
    """Compile `cart`/src into its manifest's main. Returns the module's path.
    Raises BuildError with the compiler's own words when it cannot."""
    cart = os.path.abspath(cart)
    man = manifest(cart)
    if man.get("runtime") != "wasm":
        raise BuildError('%s is not a compiled cart: its manifest says runtime %r, '
                         'and `moy build` builds "wasm" carts (SPEC.md 16)'
                         % (cart, man.get("runtime", "lua")))
    pages = man.get("memory")
    if isinstance(pages, bool) or not isinstance(pages, int) or pages < 1:
        raise BuildError('manifest.json needs "memory": the cart\'s linear memory in '
                         "64 KiB pages (SPEC.md 16.7)")
    sources = _sources(cart)
    if not sources:
        raise BuildError("no C or C++ source under %s" % os.path.join(cart, "src"))
    main = man.get("main") or "main.wasm"
    sdk = sdk or fetch_sdk(log)
    how = find_sdk()[1]
    if how == "$WASI_SDK_PATH":
        log("moy: building with $WASI_SDK_PATH (%s), not the pinned wasi-sdk %s"
            % (sdk, WASI_SDK_VERSION))
    log("moy: building %s" % _shown(cart))
    cc = os.path.join(sdk, "bin", _exe("clang"))
    cxx = os.path.join(sdk, "bin", _exe("clang++"))
    cache = _cache_dir(cart)
    os.makedirs(cache, exist_ok=True)
    includes = []
    for d in _include_dirs(cart):
        includes += ["-I", d]
    prefix = ["-ffile-prefix-map=%s%s=" % (cart, os.sep)]

    def compile_one(src):
        cplus = src.endswith(CXX_EXT)
        rel = os.path.relpath(src, cart)
        stem = hashlib.sha1(rel.encode()).hexdigest()[:10] + "_" + os.path.basename(src)
        obj = os.path.join(cache, stem + ".o")
        dep = obj[:-2] + ".d"
        flags = COMMON_FLAGS + (CXX_FLAGS if cplus else C_FLAGS) + prefix + includes
        if _library(cart, src):
            flags = flags + ["-w"]
        stamp = obj[:-2] + ".flags"
        want = json.dumps([cc if not cplus else cxx, flags])
        try:
            with open(stamp, encoding="utf-8") as f:
                same = f.read() == want
            fresh = same and os.path.isfile(obj) and \
                not _deps_newer(dep, os.stat(obj).st_mtime_ns)
        except OSError:
            fresh = False
        if fresh:
            return obj, None
        code, out = _run([cxx if cplus else cc] + flags +
                         ["-MMD", "-MF", dep, "-c", src, "-o", obj])
        if code != 0:
            return None, out
        with open(stamp, "w", encoding="utf-8") as f:
            f.write(want)
        return obj, out or None

    with ThreadPoolExecutor(max_workers=jobs or os.cpu_count() or 2) as pool:
        results = list(pool.map(compile_one, sources))
    errors = [out for obj, out in results if obj is None]
    for obj, out in results:
        if obj is not None and out:
            log(out)
    if errors:
        raise BuildError("\n".join(errors))

    objs = [obj for obj, _ in results]
    memory = pages * PAGE
    linker = cxx if any(s.endswith(CXX_EXT) for s in sources) else cc
    out = os.path.join(cache, "main.wasm")
    code, text = _run([linker, "--target=wasm32-wasi", "-nostartfiles",
                       "-Wl,--no-entry", "-Wl,--strip-all", "-Wl,--stack-first",
                       "-Wl,--export=__stack_pointer", "-Wl,--export=__heap_base",
                       "-Wl,-z,stack-size=%d" % stack,
                       "-Wl,--initial-memory=%d" % memory,
                       "-Wl,--max-memory=%d" % memory, "-o", out] + objs)
    if code != 0:
        m = re.search(r"initial memory too small, (\d+) bytes needed", text)
        if m:
            need = (int(m.group(1)) + PAGE - 1) // PAGE
            raise BuildError('the cart\'s stack and static data need %d KB, and "memory" '
                             "is %d pages (%d KB): raise it to at least %d in "
                             "manifest.json, and more for the heap"
                             % (int(m.group(1)) // 1024, pages, memory // 1024, need))
        raise BuildError(text)
    with open(out, "rb") as f:
        wasm = f.read()
    foreign = [(m, n) for m, n in module_imports(wasm) if m != "moy"]
    if foreign:
        raise BuildError(
            "the module imports %s, and a cart imports only from \"moy\" (SPEC.md "
            "16.2). Something in src/ reached the operating system -- a clock, an "
            "environment variable, a file or exit(): use the console's verbs "
            "instead (moy_time() is the clock, moy_read() the cart's own files), "
            "and keep src/runtime.c, which answers the C library's own calls."
            % ", ".join("%s.%s" % mn for mn in foreign))
    dst = os.path.join(cart, main)
    old = None
    if os.path.isfile(dst):
        with open(dst, "rb") as f:
            old = f.read()
    if old != wasm:
        tmp = dst + ".part"
        with open(tmp, "wb") as f:
            f.write(wasm)
        os.replace(tmp, dst)
    else:
        os.utime(dst)
    heap = memory - heap_base(wasm) if heap_base(wasm) is not None else None
    log("moy: built %s (%d KB; memory %d pages%s)"
        % (_shown(dst), len(wasm) // 1024, pages,
           ", %d KB of heap" % (heap // 1024) if heap is not None else ""))
    return dst


def _leb(data, i):
    result = shift = 0
    while True:
        b = data[i]
        i += 1
        result |= (b & 0x7F) << shift
        shift += 7
        if not b & 0x80:
            return result, i


def _sections(wasm):
    i = 8
    while i < len(wasm):
        sid = wasm[i]
        size, i = _leb(wasm, i + 1)
        yield sid, wasm[i:i + size]
        i += size


def module_imports(wasm):
    """[(module, name)] a module imports."""
    out = []
    for sid, body in _sections(wasm):
        if sid != 2:
            continue
        n, i = _leb(body, 0)
        for _ in range(n):
            ml, i = _leb(body, i)
            mod = body[i:i + ml].decode("utf-8", "replace")
            i += ml
            nl, i = _leb(body, i)
            name = body[i:i + nl].decode("utf-8", "replace")
            i += nl
            kind = body[i]
            i += 1
            if kind == 0:
                _t, i = _leb(body, i)
            elif kind == 1:
                i += 1
                flags, i = _leb(body, i)
                _lo, i = _leb(body, i)
                if flags & 1:
                    _hi, i = _leb(body, i)
            elif kind == 2:
                flags, i = _leb(body, i)
                _lo, i = _leb(body, i)
                if flags & 1:
                    _hi, i = _leb(body, i)
            else:
                i += 2
            out.append((mod, name))
    return out


def heap_base(wasm):
    """The exported __heap_base global's value -- where the stack and the
    static data end and the heap begins -- or None when it is not exported."""
    index = None
    for sid, body in _sections(wasm):
        if sid != 7:
            continue
        n, i = _leb(body, 0)
        for _ in range(n):
            nl, i = _leb(body, i)
            name = body[i:i + nl]
            i += nl
            kind = body[i]
            idx, i = _leb(body, i + 1)
            if kind == 3 and name == b"__heap_base":
                index = idx
    if index is None:
        return None
    imported = 0                                       # a cart imports no globals
    for sid, body in _sections(wasm):
        if sid != 6:
            continue
        n, i = _leb(body, 0)
        for g in range(n):
            i += 2                                     # value type, mutability
            if body[i] != 0x41:                        # i32.const
                return None
            v, i = _leb(body, i + 1)
            i += 1                                     # end
            if g + imported == index:
                return v
    return None


class Watcher(threading.Thread):
    """Rebuilds a compiled cart whenever a file under src/ or its manifest
    changes, until stopped. A failed build prints the compiler's words and
    leaves the last good module where it is."""

    def __init__(self, cart, log=say, period=0.4, **kw):
        threading.Thread.__init__(self, daemon=True)
        self.cart, self.log, self.period, self.kw = cart, log, period, kw
        self.stopped = threading.Event()
        self.stamp = source_stamp(cart)

    def run(self):
        while not self.stopped.wait(self.period):
            now = source_stamp(self.cart)
            if now == self.stamp:
                continue
            self.stamp = now
            try:
                build(self.cart, log=self.log, **self.kw)
            except BuildError as exc:
                self.log("moy: build failed -- the last good main.wasm keeps running\n%s"
                         % exc)
            self.stamp = source_stamp(self.cart)

    def stop(self):
        self.stopped.set()


# -- the starters -----------------------------------------------------------------


def _c_string(text):
    """`text` as the inside of a C string literal that snprintf prints as is."""
    out = []
    for ch in text:
        if ch in '"\\':
            out.append("\\" + ch)
        elif ch == "%":
            out.append("%%")
        elif 32 <= ord(ch) < 127:
            out.append(ch)
        else:
            out.append("?")
    return "".join(out)


def fetch_jet(dst, log=say):
    """Jet's files at JET_COMMIT into `dst` (src/jet/ of a new cart), each
    checked against its pin before anything is written."""
    got = {}
    for rel in sorted(JET_FILES):
        url = JET_RAW % rel
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "moy-cli"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
        except OSError as exc:
            raise BuildError("could not fetch Jet's %s: %s" % (rel, exc))
        if hashlib.sha256(data).hexdigest() != JET_FILES[rel]:
            raise BuildError("Jet's %s at %s does not hash to its pin -- refused"
                             % (rel, JET_COMMIT[:12]))
        got[rel] = data
    for rel, data in got.items():
        with open(os.path.join(dst, os.path.basename(rel)), "wb") as f:
            f.write(data)
    log("moy: fetched Jet %s (%d files, MIT) into %s"
        % (JET_COMMIT[:12], len(got), _shown(dst)))


def new_cart(dst, kind, log=say):
    """Scaffold a compiled cart at `dst` from templates/`kind`. Returns the
    title."""
    name = os.path.basename(dst.rstrip("/\\"))[:-4]
    title = name.replace("_", " ").replace("-", " ").title()
    template = os.path.join(TEMPLATES, kind)
    if not os.path.isdir(template):
        raise BuildError("no %s starter in %s" % (kind, TEMPLATES))
    os.makedirs(dst)
    try:
        man = dict(MANIFESTS[kind])
        man["title"] = title
        with open(os.path.join(dst, "manifest.json"), "w", encoding="utf-8",
                  newline="\n") as f:
            json.dump(man, f, indent=2)
            f.write("\n")
        with open(os.path.join(dst, "config.json"), "w", encoding="utf-8",
                  newline="\n") as f:
            f.write("{}\n")
        for src in _walk(template):
            rel = os.path.relpath(src, template)
            out = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(src, encoding="utf-8") as f:
                text = f.read()
            with open(out, "w", encoding="utf-8", newline="\n") as f:
                f.write(text.replace("{title}", _c_string(title)))
        if kind == "jet":
            shutil.copy(os.path.join(TEMPLATES, "wasm", "src", "runtime.c"),
                        os.path.join(dst, "src", "runtime.c"))
            os.makedirs(os.path.join(dst, "src", "jet"))
            fetch_jet(os.path.join(dst, "src", "jet"), log)
        shutil.copy(CART_HEADER, os.path.join(dst, "src", "moy_cart.h"))
    except BaseException:
        shutil.rmtree(dst, ignore_errors=True)
        raise
    return title

