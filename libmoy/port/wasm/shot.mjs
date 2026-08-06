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
 */

import { readFileSync, writeFileSync, readdirSync, statSync } from "node:fs";
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { dirname, join, relative, sep, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const RUNNER = resolve(process.env.MOY_RUNNER || join(HERE, "..", "..", "..", "runner"));
const CHROME = process.env.MOY_CHROME || "google-chrome";

const argv = process.argv.slice(2);
let cart = null, out = "shot.png", frames = 60, keys = [];
for (let i = 0; i < argv.length; i++) {
  if (argv[i] === "--frames") frames = parseInt(argv[++i], 10);
  else if (argv[i] === "--keys") keys = argv[++i].split(",").filter(Boolean);
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
await new Promise((ok) => server.listen(0, "127.0.0.1", ok));
const PORT = server.address().port;

const profile = join(process.env.TMPDIR || "/tmp", "moy-shot-" + PORT);
const chrome = spawn(CHROME, [
  "--headless=new", "--remote-debugging-port=0", "--user-data-dir=" + profile,
  "--no-first-run", "--no-default-browser-check", "--disable-gpu",
  "--window-size=900,760", "--hide-scrollbars", "--autoplay-policy=no-user-gesture-required",
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
await send("Page.navigate", { url: `http://127.0.0.1:${PORT}/` });
await new Promise((ok) => setTimeout(ok, 1500));

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
console.log("state: " + state);
if (logs.length) console.log("logs:\n  " + logs.join("\n  "));
console.log("wrote " + out);

ws.close();
chrome.kill();
server.close();
process.exit(0);
