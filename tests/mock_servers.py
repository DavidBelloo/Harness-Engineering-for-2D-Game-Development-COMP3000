"""Mock Ollama + Forge servers that speak the real HTTP APIs.

Used by test_e2e.py to exercise the whole pipeline (plan -> RAG -> code -> art -> assemble -> browser
test -> LLM repair loop) on a machine with no GPU. The mock LLM deliberately answers with a buggy
game first, then a still-wrong fix, then a good one - so the fix loop is really exercised.
"""
import base64
import hashlib
import io
import json
import math
import random
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image, ImageDraw

PLAN = {
    "title": "Ghost Dodger",
    "controls": "Left/Right arrows move",
    "rules": "Slide the ghost left and right to dodge falling pumpkins. Each pumpkin that touches you costs one of three lives. When all three lives are gone the game is over.",
    "sprites": [
        {"name": "ghost", "description": "cute white ghost with big eyes", "width": 64, "height": 64},
        {"name": "pumpkin", "description": "orange jack-o-lantern pumpkin", "width": 48, "height": 48},
    ],
    "background": "haunted graveyard at night",
    "sfx": ["hit", "pickup", "gameover"],
    "music": "spooky playful chiptune",
}

GOOD_CODE = r"""
// Ghost Dodger
const GW = 64, GH = 64, PW = 48, PH = 48;
let ghost, pumpkins, spawnTimer, lives, invincible, score;

const game = {
  over: false,
  setup() {
    ghost = { x: W / 2 - GW / 2, y: H - 100, w: GW, h: GH, speed: 340 };
    pumpkins = [];
    spawnTimer = 0.3;
    lives = 3;
    invincible = 0;
    score = 0;
    game.over = false;
    Particles.clear();
  },
  update(dt) {
    if (game.over) {
      if (Input.pressed('r') || Input.pressed('enter') || Input.pressed('space')) game.setup();
      return;
    }
    ghost.x = clamp(ghost.x + Input.axisX() * ghost.speed * dt, 0, W - ghost.w);
    invincible = Math.max(0, invincible - dt);
    spawnTimer -= dt;
    if (spawnTimer <= 0) {
      const aimed = Math.random() < 0.9;
      const x = aimed ? clamp(ghost.x + rand(-25, 25), 0, W - PW) : rand(0, W - PW);
      pumpkins.push({ x: x, y: -PH, w: PW, h: PH, vy: rand(180, 280) });
      spawnTimer = rand(0.3, 0.5);
    }
    for (const p of pumpkins) {
      p.y += p.vy * dt;
      if (rectsOverlap(ghost, p)) {
        p.dead = true;
        if (invincible <= 0) {
          lives -= 1;
          invincible = 0.5;
          SFX.play('hit');
          Anim.shake(8);
          Particles.burst(p.x + PW / 2, p.y + PH / 2, { color: '#ff8800' });
          if (lives <= 0) { game.over = true; SFX.play('gameover'); }
        }
      } else if (p.y > H) {
        p.dead = true;
        score += 1;
        SFX.play('pickup');
      }
    }
    pumpkins = pumpkins.filter(p => !p.dead);
  },
  draw(ctx) {
    Sprites.background(ctx);
    for (const p of pumpkins) Sprites.draw(ctx, 'pumpkin', p.x, p.y, p.w, p.h, { rotation: Anim.time * 2 });
    Sprites.draw(ctx, 'ghost', ghost.x, ghost.y + Anim.bob(Anim.time, 5, 4), ghost.w, ghost.h,
                 { flash: invincible > 0 ? 0.6 : 0, flipX: Input.axisX() < 0 });
    drawText(ctx, 'Score: ' + score, 16, 12);
    drawText(ctx, 'Lives: ' + lives, W - 16, 12, { align: 'right' });
    if (game.over) {
      ctx.fillStyle = 'rgba(0,0,0,0.6)';
      ctx.fillRect(0, 0, W, H);
      drawText(ctx, 'GAME OVER', W / 2, H / 2 - 50, { size: 56, align: 'center' });
      drawText(ctx, 'Press R to restart', W / 2, H / 2 + 30, { align: 'center' });
    }
  },
};
"""

# v1: syntax error (missing closing parenthesis)
BAD_SYNTAX = GOOD_CODE.replace("0, W - ghost.w);", "0, W - ghost.w;", 1)
# v2: "fixed" the syntax error but now uses a sprite name that does not exist
BAD_SPRITE = GOOD_CODE.replace("'ghost', ghost.x", "'ghostt', ghost.x")


def _fence(code, chatter=True):
    pre = "Sure! Here is the complete game:\n\n" if chatter else ""
    return pre + "```javascript\n" + code.strip("\n") + "\n```\n"


class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.chat_calls = []       # (kind, user_prompt)
        self.fix_count = 0
        self.unloads = 0
        self.embeds = 0
        self.txt2img = []          # (w, h, prompt)
        self.script = [BAD_SYNTAX, BAD_SPRITE, GOOD_CODE]   # answers to write / fix #1 / fix #2


def _embed(text, dim=96):
    v = [0.0] * dim
    for tok in re.findall(r"[a-z0-9]+", text.lower()):
        v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % dim] += 1.0
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def make_handler_ollama(state):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, obj, code=200):
            data = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/api/tags":
                return self._json({"models": [{"name": "qwen2.5-coder:7b"}, {"name": "nomic-embed-text:latest"}]})
            self._json({"error": "nope"}, 404)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if self.path == "/api/embed":
                with state.lock:
                    state.embeds += 1
                return self._json({"embeddings": [_embed(t) for t in body["input"]]})
            if self.path == "/api/generate":
                if body.get("keep_alive") == 0:
                    with state.lock:
                        state.unloads += 1
                return self._json({"done": True})
            if self.path == "/api/chat":
                msgs = body["messages"]
                system, user = msgs[0]["content"], msgs[-1]["content"]
                if "game designer" in system:
                    kind, text = "plan", json.dumps(PLAN)
                elif user.startswith("Your game code was run"):
                    with state.lock:
                        state.fix_count += 1
                        n = state.fix_count
                    kind, text = f"fix{n}", _fence(state.script[min(n, len(state.script) - 1)])
                else:
                    kind, text = "write", _fence(state.script[0])
                with state.lock:
                    state.chat_calls.append((kind, user))
                self.send_response(200)
                self.send_header("Content-Type", "application/x-ndjson")
                self.end_headers()
                for i in range(0, len(text), 40):
                    self.wfile.write((json.dumps({"message": {"role": "assistant", "content": text[i:i + 40]}, "done": False}) + "\n").encode())
                self.wfile.write((json.dumps({"done": True, "eval_count": len(text) // 4}) + "\n").encode())
                return
            self._json({"error": "unknown"}, 404)
    return H


def _creature(prompt, w, h):
    rng = random.Random(hashlib.md5(prompt.encode()).hexdigest())
    img = Image.new("RGB", (w, h), (252, 252, 252))
    d = ImageDraw.Draw(img)
    col = tuple(rng.randint(60, 230) for _ in range(3))
    cx, cy, r = w // 2, h // 2, int(min(w, h) * 0.30)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col, outline=(20, 20, 20), width=5)
    d.ellipse((cx - r // 2, cy - r // 3, cx - r // 6, cy + r // 8), fill=(255, 255, 255))
    d.ellipse((cx + r // 6, cy - r // 3, cx + r // 2, cy + r // 8), fill=(255, 255, 255))
    px = img.load()
    for _ in range(w * h // 6):                 # faint noise on the "white" background, like a real diffusion output
        x, y = rng.randrange(w), rng.randrange(h)
        p = px[x, y]
        if p[0] > 240:
            px[x, y] = tuple(max(0, c - rng.randint(0, 6)) for c in p)
    return img


def _scenery(w, h):
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        d.line((0, y, w, y), fill=(int(20 + 40 * t), int(10 + 20 * t), int(50 + 30 * t)))
    d.ellipse((w - 140, 40, w - 60, 120), fill=(235, 235, 200))
    return img


def make_handler_forge(state):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, obj, code=200):
            data = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/sdapi/v1/options":
                return self._json({"sd_model_checkpoint": "mock"})
            self._json({}, 404)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if self.path == "/sdapi/v1/unload-checkpoint":
                with state.lock:
                    state.unloads += 1
                return self._json({})
            if self.path == "/sdapi/v1/txt2img":
                w, h = body["width"], body["height"]
                with state.lock:
                    state.txt2img.append((w, h, body["prompt"]))
                img = _scenery(w, h) if "background" in body["prompt"] and "game sprite" not in body["prompt"] else _creature(body["prompt"], w, h)
                buf = io.BytesIO()
                img.save(buf, "PNG")
                return self._json({"images": [base64.b64encode(buf.getvalue()).decode()], "info": "{}"})
            self._json({}, 404)
    return H


def start(handler_factory, state):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory(state))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]
