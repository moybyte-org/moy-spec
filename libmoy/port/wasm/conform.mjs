/* The conformance player protocol, driven through the browser player's own
 * WebAssembly module.
 *
 *   node conform.mjs <cart-dir> <out.bin> [--frames N]
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
 */

import { readFileSync, readdirSync, writeFileSync, statSync } from "node:fs";
import { join, dirname, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));

const args = process.argv.slice(2);
let cart = null, out = null, frames = 2;
for (let i = 0; i < args.length; i++) {
  if (args[i] === "--frames") frames = parseInt(args[++i], 10);
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
const M = await createMoy();

/* The cart, flattened the way the page's carts.json is: names relative to the
 * cart folder, top level only. */
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
  if (name.includes("/")) continue;
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
for (let i = 0; i < frames; i++) {
  const r = M._moy_web_frame(1 / 30, 0);
  if (r === 1) { console.error("conform: " + M.UTF8ToString(M._moy_web_error())); process.exit(1); }
  if (r === 2) break;
}

const w = M._moy_web_width(), h = M._moy_web_height();
writeFileSync(out, Buffer.from(M.HEAPU8.buffer, M._moy_web_indices(), w * h));
