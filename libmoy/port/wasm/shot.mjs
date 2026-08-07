/* Screenshot the player as a BROWSER actually renders it.
 *
 *   node shot.mjs <cart.moy> [out.png] [--frames N] [--keys ArrowRight,KeyZ]
 *
 * conform.mjs runs the same wasm under node and checks its framebuffer, which
 * covers the console completely and the PAGE not at all -- canvas sizing, the
 * rAF pacing, the AudioContext, the input listeners, module loading over HTTP.
 * Bugs live in exactly that gap, and a frame dump cannot see any of them.
 *
 * So this serves the real runner/ to real headless Chrome over CDP (no
 * puppeteer -- node has a WebSocket client), lets it play, and screenshots the
 * canvas element. If this produces the right picture, the player works.
 *
 * TWO THINGS THIS CANNOT DO, learned by shipping bugs past it:
 *
 *   Pointer capability. Headless reports `hover: none, pointer: none` -- there
 *   is no input device -- and Emulation.setEmulatedMedia does not emulate those
 *   features (tried, both documented shapes). So a rule gated on
 *   `(hover: hover) and (pointer: fine)` is untestable here: the query is false
 *   in this browser whatever you do. --phone sets touch and phone metrics,
 *   which covers layout, but the has-a-mouse gate needs a real machine.
 *
 *   Anything a stylesheet decides. Assert the COMPUTED STYLE, never the class
 *   or the property the JS set. Both control bugs that reached the owner were
 *   cascade bugs where the JS was correct: `style.display = ""` fell back to
 *   the stylesheet's `none`, and `#pad .b` (1,1,0) beat `#kb` (1,0,0). A test
 *   reading `classList.contains("on")` passed through both.
 */

import { readFileSync, writeFileSync, readdirSync, statSync } from "node:fs";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { dirname, join, relative, sep, resolve } from "node:path";
import { networkInterfaces } from "node:os";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const RUNNER = resolve(process.env.MOY_RUNNER || join(HERE, "..", "..", "..", "runner"));
const CHROME = process.env.MOY_CHROME || "google-chrome";

/* THE HOST MATTERS, and this is the whole reason the default is not localhost.
 *
 * A browser gives localhost a SECURE CONTEXT and any other http origin an
 * insecure one, and AudioWorklet only exists in the former. So a player tested
 * only at 127.0.0.1 has an audio path that no LAN visitor, phone or VPN user
 * ever runs -- which is exactly how this player shipped silent to everyone but
 * the machine serving it. Default to the LAN address so the harness sees what
 * a second device sees; MOY_HOST=127.0.0.1 opts back in to the easy case. */
function lanAddress() {
    for (const list of Object.values(networkInterfaces())) {
        for (const ni of list || []) {
            if (ni.family === "IPv4" && !ni.internal) return ni.address;
        }
    }
    return "127.0.0.1";
}

const argv = process.argv.slice(2);
let cart = null, out = "shot.png", frames = 60, keys = [], phone = false;
let host = process.env.MOY_HOST || lanAddress();
for (let i = 0; i < argv.length; i++) {
  if (argv[i] === "--frames") frames = parseInt(argv[++i], 10);
  else if (argv[i] === "--keys") keys = argv[++i].split(",").filter(Boolean);
  else if (argv[i] === "--host") host = argv[++i];
  else if (argv[i] === "--phone") phone = true;
  else if (!cart) cart = argv[i];
  else out = argv[i];
}
if (!cart) {
  console.error("usage: shot.mjs <cart.moy> [out.png] [--frames N] [--keys Code,...]");
  process.exit(2);
}

/* carts.json, packed exactly as `moy run` serves it. */
function pack(dir, base = dir, into = {}) {
  const name = base.replace(/\/$/, "").split("/").pop();
  for (const f of readdirSync(dir)) {
    if (f === "thumbs" || f === "__pycache__" || f === ".git") continue;
    const p = join(dir, f);
    if (statSync(p).isDirectory()) { pack(p, base, into); continue; }
    try {
      into[name + "/" + relative(base, p).split(sep).join("/")] =
        readFileSync(p, "utf8");
    } catch (e) { /* binary: not a cart file */ }
  }
  return into;
}
const bundle = JSON.stringify(pack(resolve(cart)));

const MIME = { ".html": "text/html", ".mjs": "text/javascript", ".js": "text/javascript",
               ".wasm": "application/wasm", ".json": "application/json" };
const server = createServer((req, res) => {
  let p = decodeURIComponent(req.url.split("?")[0]);
  if (p === "/") p = "/index.html";
  if (p === "/carts.json") {
    res.writeHead(200, { "content-type": "application/json" });
    return res.end(bundle);
  }
  try {
    const body = readFileSync(join(RUNNER, p));
    res.writeHead(200, { "content-type": MIME[p.slice(p.lastIndexOf("."))] || "application/octet-stream" });
    res.end(body);
  } catch (e) { res.writeHead(404); res.end("nope"); }
});
// Bound to every interface, not just loopback: the point of the LAN default is
// that the browser reaches this over a NON-localhost origin, and a
// loopback-only server cannot be reached that way.
await new Promise((ok) => server.listen(0, "0.0.0.0", ok));
const PORT = server.address().port;

const profile = join(process.env.TMPDIR || "/tmp", "moy-shot-" + PORT);
const chrome = spawn(CHROME, [
  "--headless=new", "--remote-debugging-port=0", "--user-data-dir=" + profile,
  "--no-first-run", "--no-default-browser-check", "--disable-gpu",
  "--window-size=900,760", "--hide-scrollbars",
  // NO --autoplay-policy override. It was here, and it made every audio test
  // meaningless: the page was verified in a browser that would start sound
  // without a gesture, which no real browser does. The player shipped with no
  // way to give that gesture at all and the harness stayed green.
  "about:blank",
], { stdio: ["ignore", "ignore", "pipe"] });

const wsUrl = await new Promise((ok, err) => {
  let buf = "";
  const t = setTimeout(() => err(new Error("chrome did not report a debug port")), 20000);
  chrome.stderr.on("data", (d) => {
    buf += d;
    const m = buf.match(/ws:\/\/[^\s]+/);
    if (m) { clearTimeout(t); ok(m[0]); }
  });
});

const ws = new WebSocket(wsUrl);
await new Promise((ok) => ws.addEventListener("open", ok));
let id = 0;
const waiting = new Map();
const logs = [];
ws.addEventListener("message", (e) => {
  const m = JSON.parse(e.data);
  if (m.id && waiting.has(m.id)) { waiting.get(m.id)(m); waiting.delete(m.id); }
  if (m.method === "Runtime.consoleAPICalled")
    logs.push(m.params.args.map((a) => a.value ?? a.description ?? "").join(" "));
  if (m.method === "Runtime.exceptionThrown")
    logs.push("EXCEPTION " + (m.params.exceptionDetails?.exception?.description ||
                              m.params.exceptionDetails?.text));
});
const raw = (method, params = {}, sessionId = undefined) => new Promise((ok, err) => {
  const n = ++id;
  waiting.set(n, (m) => m.error ? err(new Error(method + ": " + JSON.stringify(m.error))) : ok(m.result));
  ws.send(JSON.stringify({ id: n, method, params, sessionId }));
});

/* The endpoint chrome prints is the BROWSER target, which has no Runtime and
 * no Page -- every evaluate against it silently answers undefined. A page
 * session is what those domains live on. */
const { targetId } = await raw("Target.createTarget", { url: "about:blank" });
const { sessionId } = await raw("Target.attachToTarget", { targetId, flatten: true });
const send = (method, params) => raw(method, params, sessionId);

const evalJS = async (expr) => {
  const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.text + " " +
    (r.exceptionDetails.exception?.description || ""));
  return r.result.value;
};

await send("Runtime.enable");
await send("Page.enable");
if (phone) {
  // The device the on-screen controls exist for: coarse pointer, touch, small
  // screen. A pad bug is invisible at desktop metrics.
  await send("Emulation.setDeviceMetricsOverride",
             { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
  await send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });
}
await send("Page.navigate", { url: `http://${host}:${PORT}/` });
await new Promise((ok) => setTimeout(ok, 2000));

// The cart is PARKED behind the start overlay until a gesture, so give it one.
// Without this the harness screenshots the overlay and reports a black game.
await send("Input.dispatchKeyEvent", { type: "keyDown", code: "Enter", key: "Enter",
                                       windowsVirtualKeyCode: 13 });
await send("Input.dispatchKeyEvent", { type: "keyUp", code: "Enter", key: "Enter",
                                       windowsVirtualKeyCode: 13 });
await new Promise((ok) => setTimeout(ok, 300));

for (const code of keys) {
  await send("Input.dispatchKeyEvent", { type: "keyDown", code, key: code, windowsVirtualKeyCode: 0 });
}
/* Let it play. rAF runs in headless Chrome, so this is real frames, not a
 * simulated clock. */
await new Promise((ok) => setTimeout(ok, Math.max(500, frames * 1000 / 60)));

const state = await evalJS("JSON.stringify(window.moy.state)");
const dataUrl = await evalJS("document.getElementById('screen').toDataURL('image/png')");
if (!dataUrl) {
  console.error("shot: no canvas. logs:\n  " + logs.join("\n  "));
  process.exit(1);
}
writeFileSync(out, Buffer.from(dataUrl.split(",")[1], "base64"));
console.log("host:  http://" + host + ":" + PORT + (phone ? "  (phone metrics)" : ""));
console.log("state: " + state);
{
  const st = JSON.parse(state || "{}");
  // The assertion that would have caught the silent player: samples must
  // actually be moving. Loud about it, because a warning nobody reads is how
  // the last one survived.
  if (st.wants && !(st.pushed > 0)) {
    console.log("!! the cart asked for audio and the page pushed NONE"
                + " (worklet=" + st.worklet + ", audio=" + st.audio + ")");
  }
}
if (logs.length) console.log("logs:\n  " + logs.join("\n  "));
console.log("wrote " + out);

ws.close();
chrome.kill();
server.close();
process.exit(0);
