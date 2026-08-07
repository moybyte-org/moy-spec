/* The page half of the moy web player.
 *
 * Everything below is platform glue -- a canvas, a keyboard, an AudioContext,
 * localStorage. It draws nothing: the console rasterizes in WebAssembly and
 * hands over finished RGBA, so this file has no idea what a sprite is. That is
 * the point of the C port, and the reason this file is ~300 lines rather than
 * the ~1500 a draw-command replayer costs.
 */

import createMoy from "./moy.mjs";

const cv = document.getElementById("screen");
const ctx = cv.getContext("2d", { alpha: false });
const statusEl = document.getElementById("status");
const titleEl = document.getElementById("title");
const padEl = document.getElementById("pad");
const startEl = document.getElementById("start");
const kbin = document.getElementById("kbin");

let M = null;                 // the wasm module
let W = 320, H = 240, fps = 30;
let img = null, running = false, rafId = 0, frames = 0, started = true;
let last = 0, t0 = 0, acc = 0;
let cartName = "";

function say(text, bad) {
  statusEl.textContent = text || "";
  statusEl.className = bad ? "bad" : "";
}

/* -- cart loading --------------------------------------------------------- */
/* carts.json is {"<cart>/<relpath>": text} -- the shape `moy run` serves live
 * and `moy export` writes beside these files. The cart name prefix is stripped
 * here so the C side sees plain names. */

async function fetchCart() {
  const r = await fetch("carts.json", { cache: "no-store" });
  if (!r.ok) throw new Error("no carts.json (" + r.status + ")");
  return r.json();
}

function feed(bundle) {
  const enc = new TextEncoder();
  for (const key of Object.keys(bundle)) {
    const slash = key.indexOf("/");
    const name = slash < 0 ? key : key.slice(slash + 1);
    if (slash > 0) cartName = key.slice(0, slash);
    if (name.indexOf("/") >= 0) continue;      // subfolders are not cart files
    const bytes = enc.encode(bundle[key]);
    const p = M._malloc(bytes.length + 1);
    M.HEAPU8.set(bytes, p);
    M.HEAPU8[p + bytes.length] = 0;
    const np = M._malloc(name.length * 4 + 1);
    M.stringToUTF8(name, np, name.length * 4 + 1);
    M._moy_web_file(np, p, bytes.length);
    M._free(np);
    M._free(p);
  }
}

/* -- persistence (SPEC.md 9) ---------------------------------------------- */
/* 256 signed 32-bit slots per cart, keyed by cart name so two games on the same
 * origin do not share a save. */

function pmemKey() { return "moy.pmem." + (cartName || "cart"); }

function pmemLoad() {
  const p = M._moy_web_pmem() >> 2;
  const raw = localStorage.getItem(pmemKey());
  const v = raw ? JSON.parse(raw) : [];
  for (let i = 0; i < 256; i++) M.HEAP32[p + i] = v[i] | 0;
  M._moy_web_pmem_clean();
}

function pmemSave() {
  if (!M._moy_web_pmem_moved()) return;
  const p = M._moy_web_pmem() >> 2;
  const v = new Array(256);
  for (let i = 0; i < 256; i++) v[i] = M.HEAP32[p + i];
  try { localStorage.setItem(pmemKey(), JSON.stringify(v)); } catch (e) { /* full or blocked */ }
  M._moy_web_pmem_clean();
}

/* -- audio (SPEC.md 8) -----------------------------------------------------
 *
 * The synth is libmoy's, in wasm. This is one AudioWorklet holding a sample
 * ring with continuous linear resampling: the console renders at its own rate
 * and the worklet reads at the context's, with no per-chunk boundary to click
 * at. Starvation DECAYS the last sample toward zero rather than hard-cutting,
 * which is the difference between a stutter and a pop.
 *
 * The loop tops the ring up to CUSHION seconds each frame rather than pushing
 * a fixed amount, so a slow frame borrows from the buffer instead of dropping
 * audio. */

const CUSHION = 0.12;
const WORKLET = `
class MoyPCM extends AudioWorkletProcessor {
  constructor() {
    super();
    this.b = new Float32Array(1 << 16); this.r = 0; this.w = 0; this.n = 0;
    this.pos = 0; this.rate = 44100; this.last = 0; this.k = 0;
    this.port.onmessage = (e) => {
      const d = e.data;
      if (d.rate) { this.rate = d.rate; return; }
      const a = d.p;
      for (let i = 0; i < a.length; i++) {
        if (this.n >= this.b.length) break;
        this.b[this.w] = a[i]; this.w = (this.w + 1) % this.b.length; this.n++;
      }
    };
  }
  process(ins, outs) {
    const o = outs[0][0], st = this.rate / sampleRate;
    for (let i = 0; i < o.length; i++) {
      if (this.n > 1) {
        const v0 = this.b[this.r], v1 = this.b[(this.r + 1) % this.b.length];
        o[i] = v0 + (v1 - v0) * this.pos; this.last = o[i]; this.pos += st;
        while (this.pos >= 1 && this.n > 1) {
          this.pos -= 1; this.r = (this.r + 1) % this.b.length; this.n--;
        }
      } else { this.last *= 0.995; o[i] = this.last; }
    }
    if (++this.k >= 8) { this.k = 0; this.port.postMessage(this.n); }
    return true;
  }
}
registerProcessor("moy-pcm", MoyPCM);
`;

let actx = null, awNode = null, awDepth = 0, audioRate = 44100, audioBlocked = false;
let audioPeak = 0, audioPushed = 0, awAnalyser = null;

function audioInit() {
  if (actx) return;
  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) return;
  try { actx = new AC(); } catch (e) { actx = null; return; }
  // AudioWorklet needs a SECURE CONTEXT. Served over plain http to anything
  // that is not localhost -- a phone on the LAN, a machine across a VPN --
  // actx.audioWorklet is undefined and there is no ring at all. That is not
  // exotic: it is what happens the first time anyone opens the player on a
  // device that is not the one running `moy run`. The chunk scheduler below is
  // the fallback, and the reason this check does not simply give up.
  if (!actx.audioWorklet) return;
  const url = URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" }));
  actx.audioWorklet.addModule(url).then(() => {
    awNode = new AudioWorkletNode(actx, "moy-pcm", { numberOfInputs: 0, outputChannelCount: [1] });
    awNode.port.onmessage = (e) => { awDepth = e.data; };
    awNode.port.postMessage({ rate: audioRate });
    // Through an analyser, so moy.level() can report what the node actually
    // OUTPUTS -- which is a different question from what we pushed into it.
    awAnalyser = actx.createAnalyser();
    awAnalyser.fftSize = 2048;
    awNode.connect(awAnalyser);
    awAnalyser.connect(actx.destination);
  }).catch(() => { awNode = null; });
}

/* Browsers refuse to start audio without a gesture. Say so in the status line
 * instead of playing silently -- "no sound on my phone" is otherwise
 * undiagnosable -- and self-heal on the first tap or key. */
function audioResume() {
  if (!actx) audioInit();
  if (!actx) return;
  // resume() is ASYNCHRONOUS. Checking actx.state straight after calling it
  // reads "suspended" every time, so clearing the notice here never fired and
  // the page went on saying "tap to enable sound" over perfectly good audio.
  // The pump re-checks each frame; this just kicks it.
  if (actx.state === "suspended") actx.resume();
}

/* FALLBACK: no AudioWorklet, so schedule each push as its own buffer source.
 * Seams between chunks are audible where the ring has none -- each chunk is
 * resampled independently and its start rounded to the context's sample grid --
 * so this is the worse path, not the equal one. It is here because silence is
 * worse still. */
let audioNext = 0;

function playChunk(f) {
  const buf = actx.createBuffer(1, f.length, audioRate);
  buf.getChannelData(0).set(f);
  const src = actx.createBufferSource();
  src.buffer = buf;
  src.connect(actx.destination);
  // A floor of currentTime + 20ms: scheduling in the past drops the chunk.
  const t = Math.max(actx.currentTime + 0.02, audioNext);
  src.start(t);
  audioNext = t + buf.duration;
}

/* Seconds still queued, whichever path is live -- what the cushion tops up. */
function audioQueuedSecs() {
  if (!actx) return 0;
  if (awNode) return awDepth / audioRate;
  return Math.max(0, audioNext - actx.currentTime);
}

function audioPump() {
  /* Only once the CART has asked for a sound. A browser suspends a fresh
   * AudioContext until a gesture, and saying so is right for a game with music
   * -- but telling someone to tap for audio a silent cart never wanted is
   * noise, and it would be on screen for the whole session. */
  if (!M._moy_web_audio_wanted()) return;
  if (!actx) return;
  if (actx.state !== "running") {
    if (!audioBlocked) { audioBlocked = true; say("tap to enable sound"); }
    return;
  }
  // Running now -- so retract the notice. This is the only place that can, and
  // it runs every frame, which is what makes it self-healing rather than
  // dependent on catching the exact moment the context flipped.
  if (audioBlocked) { audioBlocked = false; say(""); }
  const want = Math.ceil((CUSHION - audioQueuedSecs()) * audioRate);
  if (want <= 0) return;
  const ptr = M._moy_web_audio(want);
  if (!ptr) return;
  const f = new Float32Array(M.HEAPF32.buffer, ptr, want).slice();
  for (let i = 0; i < f.length; i += 16) {     // sparse: a peak meter, not a sum
    const v = f[i] < 0 ? -f[i] : f[i];
    if (v > audioPeak) audioPeak = v;
  }
  audioPushed += want;
  if (awNode) {
    awDepth += want;                           // the worklet corrects this
    awNode.port.postMessage({ p: f }, [f.buffer]);
  } else {
    playChunk(f);
  }
}

/* -- input (SPEC.md 7.3) --------------------------------------------------- */
/* One physical key per logical button, plus the arrows. That a keyboard, a
 * touchscreen and a handheld's d-pad all work unchanged is what "logical"
 * means. */

const BTN = { LEFT: 0, RIGHT: 1, UP: 2, DOWN: 3, A: 4, B: 5, RUN: 6 };
const KEYMAP = {
  ArrowLeft: BTN.LEFT, KeyA: BTN.LEFT,
  ArrowRight: BTN.RIGHT, KeyD: BTN.RIGHT,
  ArrowUp: BTN.UP, KeyW: BTN.UP,
  ArrowDown: BTN.DOWN, KeyS: BTN.DOWN,
  KeyZ: BTN.A, KeyJ: BTN.A,
  KeyX: BTN.B, KeyK: BTN.B,
  Enter: BTN.RUN, Space: BTN.RUN,
};

function asciiOf(e) {
  if (e.key.length === 1) return e.key.charCodeAt(0);
  if (e.key === "Backspace") return 8;
  if (e.key === "Enter") return 13;
  if (e.key === "Tab") return 9;
  return 0;
}

/* The gesture. Anything counts -- click, tap, key -- and it both starts the
 * cart and unlocks audio, which is the point of having one moment rather than
 * hoping the player happens to touch something. */
function begin() {
  audioResume();
  if (started) return;
  started = true;
  if (startEl) startEl.style.display = "none";
  last = performance.now();
  acc = 0;
}

function bindInput() {
  if (startEl) startEl.addEventListener("pointerdown", (e) => { begin(); e.preventDefault(); });
  addEventListener("keydown", (e) => {
    begin();
    const b = KEYMAP[e.code];
    /* While a cart is in textmode its keyboard is a TYPING keyboard: the letter
     * keys are letters, not a d-pad. The arrows still work as buttons, which is
     * what makes a text cart navigable. */
    if (b !== undefined && !(M._moy_web_textmode() && e.code.startsWith("Key"))) {
      M._moy_web_button(b, 1);
      if (e.code === "Space" || e.code.startsWith("Arrow")) e.preventDefault();
    }
    const a = asciiOf(e);
    if (a) M._moy_web_key(a, 1);
  });
  addEventListener("keyup", (e) => {
    const b = KEYMAP[e.code];
    if (b !== undefined) M._moy_web_button(b, 0);
    const a = asciiOf(e);
    if (a) M._moy_web_key(a, 0);
  });
  /* A tab that loses focus must not leave a key stuck down -- a held direction
   * survives an alt-tab otherwise and the cart walks into a wall forever. */
  addEventListener("blur", () => {
    for (let b = 0; b < 7; b++) M._moy_web_button(b, 0);
    M._moy_web_touch(0, 0, 0);
  });

  /* Pointer -> touch(), in CART coordinates: the canvas is scaled by CSS, so
   * every position goes through the element's real rect. */
  const at = (e) => {
    const r = cv.getBoundingClientRect();
    const x = Math.floor((e.clientX - r.left) / r.width * W);
    const y = Math.floor((e.clientY - r.top) / r.height * H);
    return [Math.max(0, Math.min(W - 1, x)), Math.max(0, Math.min(H - 1, y))];
  };
  cv.addEventListener("pointerdown", (e) => {
    begin();
    cv.setPointerCapture(e.pointerId);
    const [x, y] = at(e); M._moy_web_touch(x, y, 1);
    e.preventDefault();
  });
  cv.addEventListener("pointermove", (e) => {
    const [x, y] = at(e); M._moy_web_touch(x, y, e.buttons || e.pointerType === "touch" ? 1 : 0);
  });
  cv.addEventListener("pointerup", (e) => {
    const [x, y] = at(e); M._moy_web_touch(x, y, 0);
  });
  cv.addEventListener("pointercancel", () => M._moy_web_touch(0, 0, 0));
  cv.addEventListener("contextmenu", (e) => e.preventDefault());

  /* A/B: held while a finger is on them. */
  for (const el of padEl.querySelectorAll("[data-btn]")) {
    const b = BTN[el.dataset.btn];
    const set = (v) => (e) => { begin(); M._moy_web_button(b, v); e.preventDefault(); };
    el.addEventListener("pointerdown", set(1));
    el.addEventListener("pointerup", set(0));
    el.addEventListener("pointerleave", set(0));
    el.addEventListener("pointercancel", set(0));
  }

  /* THE JOYSTICK. A thumb lands somewhere near the middle of a circle and
   * slides; it does not hit 44px squares. The angle is resolved into the four
   * logical directions with a DEADZONE, so resting a thumb on the centre is not
   * a direction, and diagonals press two -- which is what a d-pad does and what
   * carts expect (SPEC.md 7.3 has four, not eight). */
  const joy = document.getElementById("joy");
  const thumb = document.getElementById("th");
  const DEAD = 0.34;
  let joyId = null;

  function joySet(dx, dy) {
    const mag = Math.hypot(dx, dy);
    M._moy_web_button(BTN.LEFT,  mag > DEAD && dx < -DEAD ? 1 : 0);
    M._moy_web_button(BTN.RIGHT, mag > DEAD && dx > DEAD ? 1 : 0);
    M._moy_web_button(BTN.UP,    mag > DEAD && dy < -DEAD ? 1 : 0);
    M._moy_web_button(BTN.DOWN,  mag > DEAD && dy > DEAD ? 1 : 0);
    const r = joy.clientWidth / 2;
    const k = mag > 1 ? 1 / mag : 1;           // clamp the thumb to the rim
    thumb.style.transform = "translate(" + (dx * k * r * 0.55) + "px,"
                                         + (dy * k * r * 0.55) + "px)";
  }

  function joyAt(e) {
    const r = joy.getBoundingClientRect();
    joySet((e.clientX - (r.left + r.width / 2)) / (r.width / 2),
           (e.clientY - (r.top + r.height / 2)) / (r.height / 2));
  }

  joy.addEventListener("pointerdown", (e) => {
    begin();
    joyId = e.pointerId;
    joy.setPointerCapture(e.pointerId);
    joyAt(e);
    e.preventDefault();
  });
  joy.addEventListener("pointermove", (e) => {
    if (joyId === e.pointerId) { joyAt(e); e.preventDefault(); }
  });
  const joyEnd = (e) => {
    if (joyId !== e.pointerId) return;
    joyId = null;
    joySet(0, 0);
    thumb.style.transform = "";
  };
  joy.addEventListener("pointerup", joyEnd);
  joy.addEventListener("pointercancel", joyEnd);

  /* The keyboard toggle: a textmode() cart on a phone has no other way to get
   * a soft keyboard up, because only a focused input summons one. */
  const kbBtn = document.getElementById("kb");
  if (kbBtn) {
    kbBtn.addEventListener("pointerdown", (e) => {
      begin();
      if (document.activeElement === kbin) kbin.blur();
      else kbin.focus();
      e.preventDefault();
    });
  }

  /* textmode wants a real soft keyboard on a phone, and only a focused input
   * summons one. It is off-screen and its value is never read -- the keydown
   * handler above is still what feeds key(). */
  kbin.addEventListener("input", () => { kbin.value = ""; });
}

/* -- the loop -------------------------------------------------------------- */

function fit() {
  const pad = 24;
  const availW = Math.max(64, innerWidth - pad);
  const availH = Math.max(64, innerHeight - (titleEl.offsetHeight + padEl.offsetHeight + pad + 24));
  const s = Math.min(availW / W, availH / H);
  cv.style.width = Math.round(W * s) + "px";
  cv.style.height = Math.round(H * s) + "px";
}
addEventListener("resize", fit);

function tick(now) {
  rafId = requestAnimationFrame(tick);
  if (!running) return;
  if (!started) { last = now; return; }
  /* SPEC.md 5: hold the cart's declared rate. rAF runs at the display's, which
   * is 60 or 120 or 144 -- a 30fps cart must not tick twice as fast on a 60Hz
   * panel just because the browser offered the frame. */
  const dt = (now - last) / 1000;
  last = now;
  acc += dt;
  const step = 1 / fps;
  if (acc < step) return;
  const use = Math.min(acc, 0.25);
  acc = 0;

  frames++;
  const r = M._moy_web_frame(use, now - t0);
  if (r === 1) { stop(M.UTF8ToString(M._moy_web_error()), true); return; }
  if (r === 2) { stop("cart exited"); return; }

  const ptr = M._moy_web_pixels();
  img.data.set(new Uint8ClampedArray(M.HEAPU8.buffer, ptr, W * H * 4));
  ctx.putImageData(img, 0, 0);
  audioPump();
  pmemSave();
}

function stop(msg, bad) {
  running = false;
  pmemSave();
  say(msg, bad);
}

async function boot() {
  const bundle = await fetchCart();
  M._moy_web_reset();
  feed(bundle);
  /* SPEC.md 9 defines rnd()'s range but not its sequence, so the seed is
   * genuinely arbitrary -- and must not be constant, or every session of a
   * cart that shuffles plays the same. */
  if (M._moy_web_boot(Date.now() & 0x7fffffff) !== 0) {
    say(M.UTF8ToString(M._moy_web_error()), true);
    return;
  }
  const err = M.UTF8ToString(M._moy_web_error());
  if (err) say(err, true);                     // non-fatal (a bad sound bank)

  W = M._moy_web_width(); H = M._moy_web_height(); fps = M._moy_web_fps();
  audioRate = M._moy_web_audio_rate();
  cv.width = W; cv.height = H;
  ctx.imageSmoothingEnabled = false;
  img = ctx.createImageData(W, H);
  document.title = M.UTF8ToString(M._moy_web_title());
  titleEl.textContent = document.title;
  fit();
  pmemLoad();

  /* The manifest's `input` list (SPEC.md 7.3) decides whether soft controls are
   * worth the screen: a touch-only cart gets none, a button cart on a phone
   * gets a pad. */
  const mf = bundle[Object.keys(bundle).find((k) => k.endsWith("/manifest.json"))];
  let hint = null;
  try { hint = JSON.parse(mf).input; } catch (e) { /* no manifest, or no hint */ }
  /* Show the pad whenever the cart uses buttons, on ANY pointer. Gating it on
   * `(pointer: coarse)` meant a desktop browser got no visible controls at all
   * -- fine if you know the keys, useless if you do not, and wrong on every
   * machine that reports a fine pointer while being used by touch (a laptop
   * with a touchscreen, a tablet in desktop mode, a remote session). The keys
   * still work; this just stops them being the only way in. */
  const wantsPad = !hint || hint.indexOf("buttons") >= 0;
    // "flex", not "": clearing the inline style falls back to the stylesheet's
  // `display: none`, so the pad was hidden on EVERY pointer type -- including
  // the touch devices it exists for. It had never once been shown.
  padEl.style.display = wantsPad ? "flex" : "none";

  /* The cart is loaded and drawn but PARKED until a gesture. See #start in the
   * page: this is the only way a browser will let audio begin, and a player
   * that boots straight in has no such moment -- it plays silently and the
   * person watching concludes it has no sound, which is exactly what happened.
   * One frame is ticked first so there is a picture behind the overlay rather
   * than a black square. */
  started = false;

  /* Build the AudioContext now rather than on the first gesture. It starts
   * suspended either way, but addModule is asynchronous -- doing it at boot
   * means the worklet is ready when a gesture arrives, instead of the first
   * sound of the game being the one that gets dropped. */
  audioInit();

  last = performance.now(); t0 = last; acc = 0;
  running = true;
  if (!rafId) rafId = requestAnimationFrame(tick);
}

/* -- dev reload ------------------------------------------------------------ */
/* `moy run` serves /stamp -- the newest mtime under the cart folder. Polling it
 * restarts the cart in place, which is faster than a page reload and keeps the
 * AudioContext (and therefore the gesture unlock) alive. */

function devWatch() {
  let seen = null;
  setInterval(async () => {
    try {
      const s = await (await fetch("stamp", { cache: "no-store" })).text();
      if (seen === null) { seen = s; return; }
      if (s !== seen) { seen = s; say("reloading…"); await boot(); }
    } catch (e) { /* the dev server went away; keep playing */ }
  }, 700);
}

/* A diagnostic handle, because this file is a module and its state is otherwise
 * unreachable from a console or a test harness. shot.mjs reads it; so can you.
 * Nothing in the player depends on it. */
window.moy = {
  /* "Is this thing on?" -- a plain oscillator through the SAME AudioContext the
   * game uses. If you hear this and not the game, the fault is in the worklet
   * or the samples; if you hear neither, the context is fine on paper and the
   * problem is downstream of this page (muted tab, output device, system
   * volume). Two seconds of A at 440Hz, quiet. */
  beep(secs) {
    audioResume();
    if (!actx) return "no AudioContext";
    const o = actx.createOscillator(), g = actx.createGain();
    o.frequency.value = 440;
    g.gain.value = 0.15;
    o.connect(g); g.connect(actx.destination);
    o.start(); o.stop(actx.currentTime + (secs || 2));
    return "beeping for " + (secs || 2) + "s; context is " + actx.state;
  },
  /* RMS of what the worklet is actually emitting, right now. Push-side metering
   * (state.peak) says the samples are good; this says whether they come out. */
  level() {
    if (!awAnalyser) return "no analyser";
    const buf = new Float32Array(awAnalyser.fftSize);
    awAnalyser.getFloatTimeDomainData(buf);
    let sum = 0, peak = 0;
    for (let i = 0; i < buf.length; i++) {
      const v = buf[i] < 0 ? -buf[i] : buf[i];
      sum += buf[i] * buf[i];
      if (v > peak) peak = v;
    }
    return { rms: Math.sqrt(sum / buf.length), peak: peak };
  },
  get state() {
    return {
      cart: cartName, running, started, frames, w: W, h: H, fps,
      audio: actx ? actx.state : "none",
      worklet: !!awNode,
      wants: M ? !!M._moy_web_audio_wanted() : false,
      queued: awNode ? awDepth / audioRate : 0,
      peak: audioPeak, pushed: audioPushed,
      dest: actx ? actx.destination.channelCount : 0,
      base: actx ? actx.baseLatency : -1,
      status: statusEl.textContent,
    };
  },
};

createMoy().then(async (mod) => {
  M = mod;
  bindInput();
  try {
    await boot();
  } catch (e) {
    say(String(e && e.message || e), true);
    return;
  }
  if (new URLSearchParams(location.search).get("dev") === "1") devWatch();
});
