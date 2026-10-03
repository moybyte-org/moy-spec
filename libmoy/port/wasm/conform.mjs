/* The conformance player protocol, driven through the browser player's own
 * WebAssembly module.
 *
 *   node conform.mjs <cart-dir> <out.bin> [--frames N] [--files DIR]
 *
 * so
 *
 *   python3 conformance/run.py --player \
 *     "node libmoy/port/wasm/conform.mjs {cart} {out}"
 *
 * checks THE SHIPPED PLAYER, not a build of libmoy that resembles it: same
 * moy.wasm, same entry points, same cart-loading path. Only the platform
 * differs -- node instead of a page -- and the platform is the part SPEC.md 0
 * says is nobody's business.
 *
 * It writes the raw index framebuffer, which is what a golden frame is, so the
 * RGBA the page uploads is never in the loop. A colour bug in the page is a
 * page bug; this checks the console.
 *
 * A compiled cart ("runtime": "wasm") runs through the shipped cart.js, as a
 * sibling module of the player's, and what is written is the last frame it
 * finished as RGB565 little-endian -- its golden's form
 * (conformance/wasm_run.py). A trap ends the run non-zero with that last
 * whole frame written; a refusal ends it non-zero with nothing written. Its
 * written files (SPEC.md 16.12) go through the page's own store, cart.js's
 * storageFiles, over a Storage kept in DIR/storage.json, where the next run
 * finds them; without --files none are kept.
 */

import { readFileSync, readdirSync, writeFileSync, statSync, renameSync } from "node:fs";
import { join, dirname, relative, sep, basename } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));

const args = process.argv.slice(2);
let cart = null, out = null, frames = 2, keep = null;
for (let i = 0; i < args.length; i++) {
  if (args[i] === "--frames") frames = parseInt(args[++i], 10);
  else if (args[i] === "--files") keep = args[++i];
  else if (args[i] === "--module") process.env.MOY_MODULE = args[++i];
  else if (!cart) cart = args[i];
  else out = args[i];
}
if (!cart || !out) {
  console.error("usage: conform.mjs <cart-dir> <out.bin> [--frames N]");
  process.exit(2);
}

/* The module lives wherever it was built. Default to the repository's runner/,
 * which is what build.sh writes and what the page loads. */
const modPath = process.env.MOY_MODULE ||
  join(HERE, "..", "..", "..", "runner", "moy.mjs");

const { default: createMoy } = await import("file://" + modPath);
const { startCart, storageFiles } = await import("file://" + join(dirname(modPath), "cart.js"));
const M = await createMoy();

/* The page's localStorage, as a file: every change written whole and renamed
 * into place, as setItem is whole. */
function folderStorage(dir) {
  const path = join(dir, "storage.json");
  let items = {};
  try { items = JSON.parse(readFileSync(path, "utf8")); } catch (e) { /* none yet */ }
  const save = () => {
    writeFileSync(path + ".new", JSON.stringify(items));
    renameSync(path + ".new", path);
  };
  return {
    get length() { return Object.keys(items).length; },
    key(i) { const k = Object.keys(items)[i]; return k === undefined ? null : k; },
    getItem(k) { return Object.prototype.hasOwnProperty.call(items, k) ? items[k] : null; },
    setItem(k, v) { items[k] = String(v); save(); },
    removeItem(k) { delete items[k]; save(); },
  };
}
M.moyFiles = storageFiles(keep ? folderStorage(keep) : null,
                          "moy.files." + basename(cart) + "/");

/* The cart, flattened the way the page's carts.json is: names relative to the
 * cart folder. */
function files(dir, base = dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) { out.push(...files(p, base)); continue; }
    out.push([relative(base, p).split(sep).join("/"), readFileSync(p)]);
  }
  return out;
}

M._moy_web_reset();
for (const [name, data] of files(cart)) {
  const p = M._malloc(data.length + 1);
  M.HEAPU8.set(data, p);
  M.HEAPU8[p + data.length] = 0;
  const np = M._malloc(name.length * 4 + 1);
  M.stringToUTF8(name, np, name.length * 4 + 1);
  M._moy_web_file(np, p, data.length);
  M._free(np);
  M._free(p);
}

/* Deterministic on purpose: a conformance frame must not depend on when it was
 * captured, so the seed is fixed and the clock stands still. */
if (M._moy_web_boot(0) !== 0) {
  console.error("conform: " + M.UTF8ToString(M._moy_web_error()));
  process.exit(1);
}

if (M._moy_web_runtime()) {
  let compiled;
  try {
    compiled = await startCart(M);
  } catch (e) {
    console.error("conform: " + (e && e.message || e));
    process.exit(1);
  }
  const bytes = M._moy_web_width() * M._moy_web_height() * 2;
  let shown = null, rc = 0;
  for (let i = 0; i < frames; i++) {
    const r = compiled.frame(1 / 30, 0);
    if (r === 1) { console.error("conform: " + compiled.error); rc = 1; break; }
    if (r === 2) break;
    const fp = M._moy_web_wasm_frame();
    shown = Buffer.from(M.HEAPU8.slice(fp, fp + bytes));
  }
  if (shown) writeFileSync(out, shown);
  process.exit(rc);
}

for (let i = 0; i < frames; i++) {
  const r = M._moy_web_frame(1 / 30, 0);
  if (r === 1) { console.error("conform: " + M.UTF8ToString(M._moy_web_error())); process.exit(1); }
  if (r === 2) break;
}

const w = M._moy_web_width(), h = M._moy_web_height();
writeFileSync(out, Buffer.from(M.HEAPU8.buffer, M._moy_web_indices(), w * h));
