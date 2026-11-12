/* ============================================================================
 * Runtime helpers for harness-generated 2D games.
 *
 * NOT a game engine: it only provides the plumbing every browser game needs
 * (fixed-timestep loop, keyboard/mouse input, Web Audio sfx + music, sprite
 * drawing, a few juice helpers). All game logic, rules and visuals are written
 * by the local LLM against this small API. The same file is injected into every
 * generated game, so the LLM never has to touch the DOM or the audio API.
 * ========================================================================== */
"use strict";

const W = 800, H = 600;

/* ---- state exposed to the automated browser test (check.py) ------------- */
const __H = window.__harness = {
  ready: false, started: false, crashed: false, frames: 0,
  over: false, won: false, score: null,
  spriteDraws: {}, sfxPlays: {}, musicMode: "none", errors: [],
};
const __ASSETS = window.__ASSETS || { title: "Game", controls: "", sprites: {}, background: null, music: null };

/* ---- small utilities ----------------------------------------------------- */
function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
function lerp(a, b, t) { return a + (b - a) * t; }
function rand(a, b) { return a + Math.random() * (b - a); }
function randInt(a, b) { return Math.floor(rand(a, b + 1)); }
function pick(arr) { return arr[Math.floor(Math.random() * arr.length)]; }
function dist(ax, ay, bx, by) { return Math.hypot(ax - bx, ay - by); }
function rectsOverlap(a, b) { return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y; }
function circlesOverlap(a, b) { return dist(a.x, a.y, b.x, b.y) < a.r + b.r; }

function drawText(ctx, text, x, y, o = {}) {
  ctx.save();
  ctx.font = (o.bold === false ? "" : "bold ") + (o.size || 24) + "px " + (o.font || "monospace");
  ctx.textAlign = o.align || "left";
  ctx.textBaseline = o.baseline || "top";
  if (o.shadow !== false) { ctx.fillStyle = "rgba(0,0,0,0.65)"; ctx.fillText(String(text), x + 2, y + 2); }
  ctx.fillStyle = o.color || "#ffffff";
  ctx.fillText(String(text), x, y);
  ctx.restore();
}

/* ---- input --------------------------------------------------------------- */
const Input = (() => {
  const held = {}, edge = {};
  const mouse = { x: W / 2, y: H / 2, down: false, pressed: false };
  const NAMES = { ArrowLeft: "left", ArrowRight: "right", ArrowUp: "up", ArrowDown: "down",
                  " ": "space", Spacebar: "space", Enter: "enter", Escape: "escape", Shift: "shift", Control: "ctrl", Tab: "tab" };
  const ALIAS = { left: ["left", "a"], right: ["right", "d"], up: ["up", "w"], down: ["down", "s"] };
  const norm = k => NAMES[k] || String(k).toLowerCase();
  const test = (map, k) => (ALIAS[norm(k)] || [norm(k)]).some(n => map[n]);
  let onFirst = null;
  return {
    mouse,
    down: k => test(held, k),
    pressed: k => test(edge, k),
    axisX() { return (this.down("right") ? 1 : 0) - (this.down("left") ? 1 : 0); },
    axisY() { return (this.down("down") ? 1 : 0) - (this.down("up") ? 1 : 0); },
    endFrame() { for (const k in edge) delete edge[k]; mouse.pressed = false; },
    clear() { for (const k in edge) delete edge[k]; },
    attach(canvas, firstInputCb) {
      onFirst = firstInputCb;
      window.addEventListener("keydown", e => {
        const k = norm(e.key);
        if (["left", "right", "up", "down", "space"].includes(k)) e.preventDefault();
        if (!held[k]) edge[k] = true;
        held[k] = true;
        if (onFirst) { const f = onFirst; onFirst = null; f(); }
      });
      window.addEventListener("keyup", e => { held[norm(e.key)] = false; });
      window.addEventListener("blur", () => { for (const k in held) held[k] = false; });
      const setPos = e => {
        const r = canvas.getBoundingClientRect();
        mouse.x = (e.clientX - r.left) * (W / r.width);
        mouse.y = (e.clientY - r.top) * (H / r.height);
      };
      canvas.addEventListener("pointermove", setPos);
      canvas.addEventListener("pointerdown", e => {
        setPos(e); mouse.down = true; mouse.pressed = true;
        if (onFirst) { const f = onFirst; onFirst = null; f(); }
      });
      window.addEventListener("pointerup", () => { mouse.down = false; });
    },
  };
})();

/* ---- sound effects (synthesised, no files needed) ------------------------ */
const SFX = {
  muted: false, _ctx: null,
  names: ["hit", "pickup", "jump", "shoot", "explosion", "powerup", "gameover", "win", "click"],
  /* each step: [type, startFreq, endFreq, seconds, volume, delay]; type "noise" ignores freqs */
  _presets: {
    hit:       [["square", 300, 70, 0.18, 0.30, 0], ["noise", 0, 0, 0.10, 0.20, 0]],
    pickup:    [["square", 660, 660, 0.07, 0.22, 0], ["square", 990, 990, 0.12, 0.22, 0.07]],
    jump:      [["triangle", 260, 620, 0.16, 0.30, 0]],
    shoot:     [["sawtooth", 900, 120, 0.12, 0.20, 0]],
    explosion: [["noise", 0, 0, 0.45, 0.35, 0], ["sawtooth", 140, 40, 0.40, 0.25, 0]],
    powerup:   [["square", 440, 440, 0.07, 0.22, 0], ["square", 554, 554, 0.07, 0.22, 0.07], ["square", 659, 659, 0.07, 0.22, 0.14], ["square", 880, 880, 0.16, 0.22, 0.21]],
    gameover:  [["sawtooth", 400, 380, 0.22, 0.28, 0], ["sawtooth", 330, 310, 0.22, 0.28, 0.24], ["sawtooth", 260, 120, 0.50, 0.28, 0.48]],
    win:       [["square", 523, 523, 0.10, 0.22, 0], ["square", 659, 659, 0.10, 0.22, 0.10], ["square", 784, 784, 0.10, 0.22, 0.20], ["square", 1047, 1047, 0.30, 0.22, 0.30]],
    click:     [["square", 800, 600, 0.04, 0.15, 0]],
  },
  _ac() {
    if (!this._ctx) { try { this._ctx = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) { this._ctx = null; } }
    return this._ctx;
  },
  _tone(a, type, f0, f1, dur, vol, delay) {
    const t = a.currentTime + delay, o = a.createOscillator(), g = a.createGain();
    o.type = type; o.frequency.setValueAtTime(f0, t); o.frequency.exponentialRampToValueAtTime(Math.max(1, f1), t + dur);
    g.gain.setValueAtTime(vol, t); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g).connect(a.destination); o.start(t); o.stop(t + dur + 0.02);
  },
  _noise(a, dur, vol, delay) {
    const t = a.currentTime + delay, n = Math.max(1, Math.floor(a.sampleRate * dur));
    const buf = a.createBuffer(1, n, a.sampleRate), d = buf.getChannelData(0);
    for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / n);
    const s = a.createBufferSource(), g = a.createGain();
    s.buffer = buf; g.gain.setValueAtTime(vol, t); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    s.connect(g).connect(a.destination); s.start(t);
  },
  play(name) {
    const steps = this._presets[name];
    if (!steps) { console.error("Unknown sound '" + name + "'. Use one of: " + this.names.join(", ")); return; }
    __H.sfxPlays[name] = (__H.sfxPlays[name] || 0) + 1;
    if (this.muted) return;
    const a = this._ac(); if (!a) return;
    if (a.state === "suspended") a.resume();
    for (const [type, f0, f1, dur, vol, delay] of steps) {
      if (type === "noise") this._noise(a, dur, vol, delay); else this._tone(a, type, f0, f1, dur, vol, delay);
    }
  },
};

/* ---- background music: AI-generated WAV if present, else a chiptune loop - */
const Music = (() => {
  let started = false, muted = false, gain = null;
  function startBuffer(a) {
    const bin = atob(__ASSETS.music.split(",")[1]), bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return a.decodeAudioData(bytes.buffer).then(buf => {
      const src = a.createBufferSource(); src.buffer = buf; src.loop = true;
      gain = a.createGain(); gain.gain.value = muted ? 0 : 0.35;
      src.connect(gain).connect(a.destination); src.start(); __H.musicMode = "file";
    });
  }
  function startChiptune(a) {
    __H.musicMode = "chiptune";
    gain = a.createGain(); gain.gain.value = muted ? 0 : 0.12; gain.connect(a.destination);
    let seed = 7; for (const ch of String(__ASSETS.title)) seed = (seed * 31 + ch.charCodeAt(0)) >>> 0;
    const rnd = () => (seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296;
    const scale = rnd() < 0.6 ? [0, 2, 3, 5, 7, 8, 10] : [0, 2, 4, 5, 7, 9, 11];
    const root = 40 + Math.floor(rnd() * 7), step = 60 / (110 + Math.floor(rnd() * 40)) / 2;
    const midi = n => 440 * Math.pow(2, (n - 69) / 12);
    const lead = Array.from({ length: 16 }, () => scale[Math.floor(rnd() * scale.length)]);
    const note = (f, t, d, type, v) => {
      const o = a.createOscillator(), g = a.createGain(); o.type = type; o.frequency.value = f;
      g.gain.setValueAtTime(v, t); g.gain.exponentialRampToValueAtTime(0.0001, t + d);
      o.connect(g).connect(gain); o.start(t); o.stop(t + d + 0.02);
    };
    let next = a.currentTime + 0.1, i = 0;
    setInterval(() => {
      while (next < a.currentTime + 0.3) {
        const k = i % 16;
        if (k % 4 === 0) note(midi(root + scale[((k / 4) * 2) % 7 | 0]), next, step * 3.5, "triangle", 0.5);
        note(midi(root + 24 + lead[k]), next, step * 0.9, "square", 0.22);
        next += step; i++;
      }
    }, 50);
  }
  return {
    start() {
      if (started) return; started = true;
      const a = SFX._ac(); if (!a) return;
      if (a.state === "suspended") a.resume();
      if (__ASSETS.music) startBuffer(a).catch(e => { console.warn("Music decode failed, using chiptune:", e); startChiptune(a); });
      else startChiptune(a);
    },
    setMuted(m) { muted = m; if (gain) gain.gain.value = m ? 0 : (__H.musicMode === "file" ? 0.35 : 0.12); },
  };
})();

/* ---- sprites ------------------------------------------------------------- */
const Sprites = {
  imgs: {}, _warned: {}, _tmp: null,
  has(name) { return !!this.imgs[name]; },
  size(name) { const i = this.imgs[name]; return i ? { w: i.naturalWidth, h: i.naturalHeight } : null; },
  /* x,y = top-left of the box. w,h optional (default: natural size).
     opts: { rotation (radians), flipX, flipY, alpha, scale, flash (0..1 white tint) } */
  draw(ctx, name, x, y, w, h, o = {}) {
    const img = this.imgs[name];
    if (!img) {
      if (!this._warned[name]) {
        this._warned[name] = true;
        console.error("Unknown sprite '" + name + "'. Available sprites: " + (Object.keys(this.imgs).filter(k => k.indexOf("__") !== 0).join(", ") || "(none)"));
      }
      ctx.fillStyle = "#ff00ff"; ctx.fillRect(x, y, w || 32, h || 32); return;
    }
    w = w || img.naturalWidth; h = h || img.naturalHeight;
    __H.spriteDraws[name] = (__H.spriteDraws[name] || 0) + 1;
    const sc = o.scale == null ? 1 : o.scale;
    ctx.save();
    ctx.globalAlpha = o.alpha == null ? 1 : o.alpha;
    ctx.translate(x + w / 2, y + h / 2);
    if (o.rotation) ctx.rotate(o.rotation);
    ctx.scale((o.flipX ? -1 : 1) * sc, (o.flipY ? -1 : 1) * sc);
    ctx.imageSmoothingEnabled = false;
    if (o.flash > 0) {
      const c = this._tmp || (this._tmp = document.createElement("canvas"));
      c.width = Math.max(1, Math.round(w)); c.height = Math.max(1, Math.round(h));
      const t = c.getContext("2d"); t.imageSmoothingEnabled = false;
      t.drawImage(img, 0, 0, c.width, c.height);
      t.globalCompositeOperation = "source-atop"; t.fillStyle = "rgba(255,255,255," + o.flash + ")"; t.fillRect(0, 0, c.width, c.height);
      ctx.drawImage(c, -w / 2, -h / 2, w, h);
    } else {
      ctx.drawImage(img, -w / 2, -h / 2, w, h);
    }
    ctx.restore();
  },
  background(ctx) {
    if (this.imgs.__background) { ctx.imageSmoothingEnabled = false; ctx.drawImage(this.imgs.__background, 0, 0, W, H); return; }
    const g = ctx.createLinearGradient(0, 0, 0, H); g.addColorStop(0, "#1b1b3a"); g.addColorStop(1, "#0b0b18");
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  },
};

/* ---- animation + juice --------------------------------------------------- */
const Anim = {
  time: 0, _shakeT: 0, _shakeDur: 0.25, _shakeMag: 0,
  bob(t = Anim.time, amp = 4, speed = 4) { return Math.sin(t * speed) * amp; },
  pulse(t = Anim.time, amount = 0.08, speed = 6) { return 1 + Math.sin(t * speed) * amount; },
  shake(mag = 8, dur = 0.25) { this._shakeMag = mag; this._shakeDur = dur; this._shakeT = dur; },
  _apply(ctx, dt) {
    if (this._shakeT > 0) {
      this._shakeT -= dt;
      const m = this._shakeMag * Math.max(0, this._shakeT / this._shakeDur);
      ctx.translate((Math.random() * 2 - 1) * m, (Math.random() * 2 - 1) * m);
    }
  },
};

const Particles = {
  list: [],
  burst(x, y, o = {}) {
    const n = o.count == null ? 12 : o.count;
    for (let i = 0; i < n; i++) {
      const ang = Math.random() * Math.PI * 2, sp = (o.speed || 160) * (0.4 + Math.random() * 0.6);
      this.list.push({ x, y, vx: Math.cos(ang) * sp, vy: Math.sin(ang) * sp, life: o.life || 0.5, max: o.life || 0.5,
                       size: o.size || 4, color: o.color || "#ffffff", g: o.gravity || 0 });
    }
  },
  update(dt) {
    for (const p of this.list) { p.life -= dt; p.vy += p.g * dt; p.x += p.vx * dt; p.y += p.vy * dt; }
    this.list = this.list.filter(p => p.life > 0);
  },
  draw(ctx) {
    for (const p of this.list) { ctx.globalAlpha = Math.max(0, p.life / p.max); ctx.fillStyle = p.color; ctx.fillRect(p.x - p.size / 2, p.y - p.size / 2, p.size, p.size); }
    ctx.globalAlpha = 1;
  },
  clear() { this.list.length = 0; },
};

/* ---- bootstrap: asset loading, splash screen, main loop ------------------ */
function loadImage(uri) {
  return new Promise((resolve, reject) => { const i = new Image(); i.onload = () => resolve(i); i.onerror = () => reject(new Error("image failed to decode")); i.src = uri; });
}

function startGame(game) {
  const canvas = document.getElementById("c"), ctx = canvas.getContext("2d");
  ctx.imageSmoothingEnabled = false;
  if (!game || typeof game.update !== "function" || typeof game.draw !== "function") {
    console.error("Game code must define: const game = { setup() {}, update(dt) {}, draw(ctx) {} }");
    __H.crashed = true; __H.ready = true; return;
  }
  let started = false, paused = false, last = performance.now();

  const crash = (e, phase) => {
    __H.crashed = true;
    const msg = "Runtime error in game." + phase + "(): " + (e && e.message) + "\n" + (e && e.stack);
    __H.errors.push(msg); console.error(msg);
  };
  const begin = () => {
    started = true; __H.started = true; Input.clear(); last = performance.now();
    SFX._ac(); Music.start();
  };
  Input.attach(canvas, begin);

  const loads = Object.entries(__ASSETS.sprites || {}).map(([n, uri]) => loadImage(uri).then(i => { Sprites.imgs[n] = i; }));
  if (__ASSETS.background) loads.push(loadImage(__ASSETS.background).then(i => { Sprites.imgs.__background = i; }));

  Promise.all(loads).catch(e => console.error("Asset loading failed: " + e.message)).then(() => {
    try { if (game.setup) game.setup(); } catch (e) { crash(e, "setup"); }
    __H.ready = true;
    requestAnimationFrame(frame);
  });

  function splash() {
    ctx.fillStyle = "rgba(0,0,0,0.62)"; ctx.fillRect(0, 0, W, H);
    drawText(ctx, __ASSETS.title, W / 2, H / 2 - 90, { size: 48, align: "center" });
    if (__ASSETS.controls) drawText(ctx, __ASSETS.controls, W / 2, H / 2 - 10, { size: 20, align: "center", color: "#cfd8ff" });
    drawText(ctx, "Press any key or click to start", W / 2, H / 2 + 50, { size: 22, align: "center", color: "#ffe28a" });
    drawText(ctx, "M = mute   P = pause", W / 2, H - 40, { size: 16, align: "center", color: "#9aa3c7" });
  }
  function frame(now) {
    const dt = Math.min(0.05, (now - last) / 1000); last = now;
    if (__H.crashed) {
      ctx.fillStyle = "#300"; ctx.fillRect(0, 0, W, 90);
      drawText(ctx, "GAME CRASHED - see console", 16, 16, { size: 22, color: "#ff8080" });
      return;
    }
    if (started && Input.pressed("m")) { SFX.muted = !SFX.muted; Music.setMuted(SFX.muted); }
    if (started && Input.pressed("p")) paused = !paused;
    try {
      if (started && !paused) { Anim.time += dt; game.update(dt); Particles.update(dt); }
    } catch (e) { crash(e, "update"); }
    if (!__H.crashed) {
      try {
        ctx.save(); ctx.imageSmoothingEnabled = false; Anim._apply(ctx, started && !paused ? dt : 0);
        game.draw(ctx); ctx.restore(); Particles.draw(ctx);
        if (!started) splash();
        else if (paused) { ctx.fillStyle = "rgba(0,0,0,0.5)"; ctx.fillRect(0, 0, W, H); drawText(ctx, "PAUSED", W / 2, H / 2 - 20, { size: 48, align: "center" }); }
      } catch (e) { try { ctx.restore(); } catch (_) {} crash(e, "draw"); }
    }
    Input.endFrame();
    __H.frames++; __H.over = !!game.over; __H.won = !!game.won; __H.score = (game.score == null ? null : game.score);
    requestAnimationFrame(frame);
  }
}
