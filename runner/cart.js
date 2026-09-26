/* A compiled cart ("runtime": "wasm"), run beside the console as a SIBLING
 * WebAssembly module.
 *
 * The browser's own engine instantiates the cart's main.wasm. Its imports
 * from "moy" are adapters over the import table libmoy's wasm binding exports
 * (src/moy_wasm.c, built into moy.wasm by cart.c): every verb the cart calls
 * is that C function, with the same marshalling, the same blit and read, the
 * same traps as on every other host. Never a wasm engine inside the wasm
 * console.
 *
 * The two modules have separate memories, so every pointer the cart hands
 * over is an offset into ITS memory, which the C side cannot address. The
 * adapters are generated from the table's own signature strings, and where a
 * row says '*~' -- a pointer and the length it covers -- the range is
 * bounds-checked against the cart's memory, copied into the console's, passed
 * to C as that copy, and copied back when the call returns. The pointers a
 * row carries as a plain i32 (blit's frame, camera's out) are the binding's
 * to reach, and it reaches them through span() and store() below. A trap
 * from the binding is thrown as a JavaScript exception, which unwinds the
 * cart exactly as a wasm trap does.
 *
 * Used by player.js in the page and by conform.mjs under node.
 */

const OUT_OF_BOUNDS = "out of bounds memory access";
const HOOK = { init: 0, update: 1, draw: 2 };

export class CartTrap extends Error {}

/* The import table, read out of the console's memory: name, the C function
 * it binds, and WAMR's signature string for the rest of its arguments. */
function table(M) {
  const cp = M._malloc(4);
  const base = M._moy_web_natives(cp);
  const n = M.HEAPU32[cp >> 2];
  M._free(cp);
  const rows = [];
  for (let i = 0; i < n; i++) {
    const at = (base >> 2) + i * 4;           // NativeSymbol: four 32-bit words
    rows.push({
      name: M.UTF8ToString(M.HEAPU32[at]),
      fn: M.wasmTable.get(M.HEAPU32[at + 1]),
      sig: M.UTF8ToString(M.HEAPU32[at + 2]),
    });
  }
  return rows;
}

/* '*~' is one pointer-and-length pair; every other letter one scalar. */
function params(sig) {
  const inner = /^\((.*)\)(.?)$/.exec(sig)[1];
  const out = [];
  for (let k = 0; k < inner.length; k++) {
    if (inner[k] === "*" && inner[k + 1] === "~") { out.push("span"); k++; }
    else out.push(inner[k]);
  }
  return out;
}

/* Boot a compiled cart the console has already checked and bound
 * (moy_web_boot, which refuses a module the proposal's shape does not allow
 * before anything here runs). Instantiates it and runs _init. Resolves to
 * the cart, or rejects with the reason it did not start. */
export async function startCart(M) {
  const w = M._moy_web_binding();
  const lp = M._malloc(4);
  const mp = M._moy_web_module(lp);
  const len = M.HEAP32[lp >> 2];
  M._free(lp);
  const module = M.HEAPU8.slice(mp, mp + len);

  let memory = null;
  let owned = [];                             // the console copies of this call

  const cartBytes = () => new Uint8Array(memory.buffer);
  const scratch = (n) => {
    const p = M._malloc(n > 0 ? n : 1);
    owned.push(p);
    return p;
  };

  /* The binding's two reaches into the cart's memory (moy_wasm_js_span and
   * moy_wasm_js_store, cart.c). */
  M.moyCart = {
    span(off, n) {
      const mem = cartBytes();
      if (off + n > mem.length) return 0;
      const p = scratch(n);
      M.HEAPU8.set(mem.subarray(off, off + n), p);
      return p;
    },
    store(off, src, n) {
      const mem = cartBytes();
      if (off + n > mem.length) return 0;
      mem.set(M.HEAPU8.subarray(src, src + n), off);
      return 1;
    },
  };

  const imports = {};
  for (const row of table(M)) {
    const kinds = params(row.sig);
    imports[row.name] = (...args) => {
      if (!memory) throw new CartTrap("moy: an import ran before the cart was bound");
      const cargs = [w];
      const copies = [];
      let a = 0;
      owned = [];
      try {
        for (const k of kinds) {
          if (k !== "span") { cargs.push(args[a++]); continue; }
          const off = args[a++] >>> 0, n = args[a++] >>> 0;
          const mem = cartBytes();
          if (off + n > mem.length) throw new CartTrap(OUT_OF_BOUNDS);
          const p = scratch(n);
          M.HEAPU8.set(mem.subarray(off, off + n), p);
          copies.push([off, p, n]);
          cargs.push(p, n);
        }
        const r = row.fn(...cargs);
        for (const [off, p, n] of copies) cartBytes().set(M.HEAPU8.subarray(p, p + n), off);
        const trapped = M._moy_web_trapped(w);
        if (trapped) throw new CartTrap(M.UTF8ToString(trapped));
        return r;
      } finally {
        for (const p of owned) M._free(p);
        owned = [];
      }
    };
  }

  let instance;
  try {
    ({ instance } = await WebAssembly.instantiate(module, { moy: imports }));
  } catch (e) {
    throw new Error("this cart does not start: " + (e && e.message || e));
  }
  memory = instance.exports.memory;
  const ex = instance.exports;

  const cart = {
    error: "",
    dead: false,
    /* One hook, bracketed by the binding. 0 when it returned or the cart
     * quit; 1 when it trapped, with the message in cart.error. */
    hook(h, arg) {
      M._moy_web_begin(w, h);
      let threw = null;
      try {
        if (h === HOOK.init) ex._init();
        else if (h === HOOK.update) ex._update(arg);
        else ex._draw();
      } catch (e) {
        threw = e;
      }
      if (!M._moy_web_end(w, threw ? 1 : 0)) return 0;
      const t = M._moy_web_trapped(w);
      cart.error = t ? M.UTF8ToString(t) : String(threw && threw.message || threw);
      cart.dead = true;
      return 1;
    },
    /* One tick, as moy_web_frame is for a Lua cart: 0 while running, 1 when
     * it trapped, 2 when it quit. The page's RGBA changes only when _draw
     * finished. */
    frame(dt, tMs) {
      if (cart.dead) return 1;
      M._moy_web_wasm_tick(tMs);
      if (cart.hook(HOOK.update, dt)) return 1;
      if (!M._moy_web_running()) return 2;
      if (cart.hook(HOOK.draw)) return 1;
      M._moy_web_wasm_present();
      return M._moy_web_running() ? 0 : 2;
    },
  };
  if (cart.hook(HOOK.init)) throw new Error("_init: " + cart.error);
  return cart;
}
