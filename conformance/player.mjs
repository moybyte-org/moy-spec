// Run a conformance cart through the SHIPPED WebAssembly player and dump the
// frame it produces -- headless, in plain node, with no npm and no browser.
//
//   node conformance/player.mjs <cart-dir> <out-file>
//   python3 conformance/run.py --player "node conformance/player.mjs {cart} {out}"
//
// This is the implementation SPEC.md 11 names as the tiebreaker for golden
// frames, so it is the one that ought to be producing them.
//
// HOW IT GETS A PICTURE, since the answer is not obvious. The spec build of the
// player rasterizes NOTHING in the wasm: on the handheld tier the system canvas
// IS the game canvas and both are CommandCanvas, so the Python side emits a
// stream of draw commands and the PAGE rasterizes them in JavaScript. There is
// no framebuffer inside the wasm to read.
//
// So the rasterizer we need is the page's. Rather than vendoring a copy of it
// here -- which would drift silently the next time runner/index.html is
// regenerated -- this EXTRACTS it at run time: pull the non-module <script>
// blocks out of the shipped page, evaluate them in a node:vm context behind a
// small DOM shim, and call the replayer's own rep() against its own idx
// framebuffer. There is no copy, so there is nothing to drift. If the page ever
// changes shape enough that extraction fails, it fails LOUDLY with a
// ReferenceError rather than quietly testing stale code.
//
// That also makes this the project's only INDEPENDENT check. moycore was
// extracted from the reference console's rasterizer, so the two share a
// lineage and agreement between them cannot catch a bug that was always there.
// The page's replayer is hand-written JavaScript that shares no code with
// either -- so where it agrees, the agreement means something.
//
// When moybyte's build.sh grows a proper replay.mjs output, delete the
// extraction block below and import it. Nothing else here changes.

import { readFileSync, readdirSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(join(HERE, ".."));
const RUNNER = process.env.MOY_RUNNER || join(ROOT, "runner");

const CART = process.argv[2];
const OUT = process.argv[3];
const FRAMES = parseInt(process.env.MOY_FRAMES || "3", 10);
// The console draws a bottom-right FPS chip over the cart's own canvas
// (runtime/perf_hud.py, gated on ws.show_fps which defaults True). It is host
// chrome, not the cart, and a golden frame must not contain it.
const HUD = process.env.MOY_HUD === "1";

if (!CART || !OUT) {
    console.error("usage: node conformance/player.mjs <cart-dir> <out-file>");
    process.exit(2);
}

const noop = () => {};

// --- 1. the replayer, lifted out of the shipped page ------------------------

function loadReplayer() {
    const html = readFileSync(join(RUNNER, "index.html"), "utf-8");
    const blocks = [...html.matchAll(/<script(?![^>]*type=module)[^>]*>([\s\S]*?)<\/script>/g)]
        .map((m) => m[1]);
    if (!blocks.length) throw new Error("no plain <script> block in runner/index.html");

    // Everything the page's top-level code touches on its way to defining the
    // replayer. Stubs, not a DOM: we never lay anything out, we only need the
    // functions to come into scope.
    const ctx2d = {
        createImageData: (w, h) => ({ data: new Uint8ClampedArray(w * h * 4), width: w, height: h }),
        putImageData: noop, imageSmoothingEnabled: false, fillRect: noop, clearRect: noop,
    };
    const el = () => new Proxy({}, {
        get: (t, k) => {
            if (k === "getContext") return () => ctx2d;
            if (k === "getBoundingClientRect") return () => ({ left: 0, top: 0, width: 320, height: 240 });
            if (k === "style") return {};
            if (k === "classList") return { add: noop, remove: noop, toggle: noop, contains: () => false };
            if (k in t) return t[k];
            return noop;
        },
        set: (t, k, v) => ((t[k] = v), true),
    });
    const sandbox = {
        document: {
            getElementById: el, createElement: el, querySelector: el, querySelectorAll: () => [],
            body: el(), documentElement: el(), head: el(), addEventListener: noop, hidden: false,
        },
        navigator: { userAgent: "node", getGamepads: () => [], maxTouchPoints: 0 },
        console, setTimeout, clearTimeout, setInterval, clearInterval, requestAnimationFrame: noop,
        URLSearchParams, URL, TextDecoder, TextEncoder, Blob: class {},
        Uint8Array, Uint8ClampedArray, Int16Array, Int32Array, Float32Array,
        Math, JSON, Date, Object, Array, String, Number, Boolean, Promise, Error,
        parseInt, parseFloat, isNaN, isFinite,
    };
    sandbox.window = {
        addEventListener: noop, removeEventListener: noop, devicePixelRatio: 1,
        innerWidth: 800, innerHeight: 600, location: { href: "", search: "" },
        matchMedia: () => ({ matches: false, addEventListener: noop }),
        document: sandbox.document, URL, Blob: sandbox.Blob,
    };
    sandbox.globalThis = sandbox;
    vm.createContext(sandbox);
    // The page's top-level code runs for its side effect of DECLARING the
    // replayer; it is expected to stop early on some browser-only global, and
    // that is fine -- function declarations hoist, so rep() and friends are in
    // scope regardless. What is not fine is rep() missing, which is checked below.
    for (const src of blocks) {
        try { vm.runInContext(src, sandbox); } catch (e) { /* browser-only path */ }
    }
    for (const fn of ["df", "rep", "alloc", "rs"]) {
        if (typeof sandbox[fn] !== "function") {
            throw new Error(
                "could not extract the replayer from runner/index.html: " + fn + " is missing. " +
                "The page's shape changed; see the note at the top of this file.");
        }
    }
    return sandbox;
}

// --- 2. the shipped wasm player, booted headlessly --------------------------

async function bootPlayer(cartDir) {
    const { loadMicroPython } = await import(
        pathToFileURL(join(RUNNER, "micropython.mjs")).href);
    const mp = await loadMicroPython({ heapsize: 48 * 1024 * 1024, stdout: (l) => { if (process.env.MOY_VERBOSE) console.error("[player]", l); } });
    const mkdirs = (p) => {
        let c = "";
        for (const s of p.split("/")) { if (!s) continue; c += "/" + s; try { mp.FS.mkdir(c); } catch (e) {} }
    };
    const name = cartDir.replace(/\/+$/, "").split("/").pop();
    mkdirs("/moy/carts/" + name);
    for (const f of readdirSync(cartDir)) {
        mp.FS.writeFile("/moy/carts/" + name + "/" + f,
                        readFileSync(join(cartDir, f), "utf-8"));
    }
    // hud=False keeps the console's bottom-right FPS chip out of the cart's own
    // raster. Players built before that parameter existed reject the keyword, so
    // fall back to clearing the flag on the live Workstation -- same effect,
    // reaching into a private singleton to get it. Try the supported path first.
    const bootCall = (hudArg) =>
        "import web_boot\n" +
        "web_boot.boot('/moy/carts', cart=" + JSON.stringify(name) + hudArg + ")\n" +
        "from web_boot import assets_json, step_frame_json";
    let legacy = false;
    if (HUD) {
        mp.runPython(bootCall(""));
    } else {
        try {
            mp.runPython(bootCall(", hud=False"));
        } catch (e) {
            if (!/unexpected keyword argument/.test(String(e.message || e))) throw e;
            legacy = true;
            mp.runPython(bootCall(""));
            mp.runPython(
                "import web_boot as _wb\n" +
                "_ws = _wb._S.get('ws')\n" +
                "if _ws is not None:\n" +
                "    _ws.show_fps = False\n" +
                "    _ws.perf_hud = False\n");
        }
    }
    if (process.env.MOY_VERBOSE) {
        console.error("[harness] hud suppression: %s",
                      HUD ? "off (chip will draw)" : (legacy ? "legacy flag poke" : "hud=False"));
    }
    return mp;
}

// --- 3. the player's own assets + stream, through the page's own replayer ----

const page = loadReplayer();
const mp = await bootPlayer(CART);
const assetsJson = mp.globals.get("assets_json")();
const assets = JSON.parse(assetsJson);
const step = mp.globals.get("step_frame_json");

// The page reaches its transport through a global `MOY` (defined in the module
// script, which is the wasm loader we deliberately do not run). Here the
// harness IS the transport, so supply the one method the replay path calls:
// df() re-fetches assets when a layer's imgref misses the cache.
page.MOY = { assets: () => assetsJson };

page.W = assets.w;
page.H = assets.h;
page.PAL = assets.palette;
page.FONT = assets.font;
page.SHEET = assets.sheet || null;
page.alloc();

// Hand each frame to the page's OWN handler, df(), rather than picking
// .cmds out of the payload here. The payload shape is a moving target -- the
// build this was written against ships a flat `cmds` list, a newer one slices
// the frame into per-surface streams under `surfaces` with a {"same":1}
// delta-cache -- and df() is the code that already knows which is which. Read
// the payload directly and the harness silently renders a blank frame the day
// the protocol moves; go through df() and it just keeps working.
let frames = 0;
for (let i = 0; i < FRAMES; i++) {
    page.df(JSON.parse(step(1.0 / 30)));
    frames++;
}

const idx = page.idx;
if (!idx || idx.length !== assets.w * assets.h) {
    console.error("replayer produced %s bytes, expected %d",
                  idx ? idx.length : "no", assets.w * assets.h);
    process.exit(1);
}
writeFileSync(OUT, Buffer.from(idx));
if (process.env.MOY_VERBOSE) {
    console.error("%s: %d frames -> %d bytes", CART, frames, idx.length);
}
