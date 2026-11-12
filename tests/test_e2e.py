"""End-to-end test of the whole pipeline against mock Ollama + Forge servers.

    python tests/test_e2e.py

Needs: requests, numpy, pillow, playwright (+ a Chromium/Edge/Chrome browser). No GPU, no models.
Covers: plan -> RAG -> code -> art + cut-out -> assemble -> real browser test -> LLM repair loop,
plus the music path (a synthetic WAV stands in for MusicGen) and the --skip-art path.
"""
import json
import math
import re
import sys
import tempfile
from argparse import Namespace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import mock_servers as ms  # noqa: E402
from pipeline import config, music, planner, coder, rag  # noqa: E402
import harness  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"  [{'ok' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not cond else ""))


def fake_music(prompt, out_wav, seconds=None):
    sr = 22050
    t = np.arange(sr * 3) / sr
    wav = (0.5 * np.sin(2 * math.pi * 220 * t) + 0.3 * np.sin(2 * math.pi * 330 * t)).astype(np.float32)
    music.write_wav(out_wav, music.loopify(wav, sr, 0.5), sr)
    return Path(out_wav)


def main():
    tmp = Path(tempfile.mkdtemp(prefix="harness_e2e_"))
    ostate, fstate = ms.State(), ms.State()
    osrv, oport = ms.start(ms.make_handler_ollama, ostate)
    fsrv, fport = ms.start(ms.make_handler_forge, fstate)
    config.OLLAMA_URL, config.FORGE_URL, config.OUTPUT_DIR = f"http://127.0.0.1:{oport}", f"http://127.0.0.1:{fport}", tmp
    config.CACHE_DIR = tmp / "cache"

    print("\n--- unit checks ---")
    check("plan normaliser repairs junk", planner.normalise({"sprites": ["a b c", {"name": "x"}], "sfx": ["boom", "hit"]}, "idea")["sprites"][0]["name"] == "a_b_c")
    check("plan normaliser filters unknown sfx", "boom" not in planner.normalise({"sfx": ["boom"]}, "idea")["sfx"])
    check("extract_code: fenced + chatter", coder.extract_code("Sure\n```js\nconst game = {update(){},draw(){}};\n```\nbye").startswith("const game"))
    check("extract_code: unterminated fence", "const game" in coder.extract_code("```javascript\nconst game = {update(){},draw(){}};\n"))
    check("extract_code: full html page", "const game" in coder.extract_code("<html><script>const game={update(){},draw(){}};</script></html>"))
    check("validate rejects missing game", bool(coder.validate("let x = 1;")))

    r = rag.Retriever()
    hits = [d.id for d, _ in r.search("a ghost dodging falling pumpkins", 3)]
    check("RAG (hybrid) finds falling-objects doc", r.method == "hybrid" and "01-falling-objects" in hits, f"{r.method} {hits}")
    r2 = rag.Retriever(use_embeddings=False)
    expect = {"a ghost dodging falling pumpkins, you lose after three hits": {"01-falling-objects"},
              "a cat flying a rocket and shooting asteroids": {"02-shooter-bullets"},
              "a knight running through a castle, jumping over fire pits and collecting coins": {"03-platformer-physics", "13-runner-scrolling"},
              "a little robot collecting batteries in a maze while avoiding patrol drones": {"04-topdown-movement"},
              "a hungry caterpillar eating leaves in a garden and growing longer": {"12-grid-games"},
              "an underwater game where you click bubbles to pop them before they reach the surface": {"15-mouse-click-games"}}
    for idea, want in expect.items():
        got = [d.id for d, _ in r2.search(idea + " Lose when you run out of lives. Game over.", 3)]
        check(f"RAG keyword fallback -> {sorted(want)[0][:18]} for '{idea[:34]}...'", bool(want & set(got)), str(got))

    print("\n--- scenario A: full pipeline, art via mock Forge, fake MusicGen, buggy code -> repaired ---")
    music_orig = music.generate
    music.generate = fake_music
    args = Namespace(skip_art=False, no_music=False, music_seconds=3, max_fixes=3, soak=9, open=False)
    rec = harness.run_one("a ghost dodging falling pumpkins, you lose after three hits", args, r)
    music.generate = music_orig
    run_dir = Path(rec["run_dir"])
    html = (run_dir / "game.html").read_text(encoding="utf-8")
    check("final game passed the browser test", rec["passed"], json.dumps([a["errors"] for a in rec["attempts"]])[:400])
    check("needed exactly 2 LLM repair rounds", rec["fix_rounds"] == 2, str(rec["fix_rounds"]))
    check("round 0 failed on the syntax error with a line number", "at line" in " ".join(rec["attempts"][0]["errors"]) and "SyntaxError" in " ".join(rec["attempts"][0]["errors"]))
    check("round 1 failed on the unknown sprite", any("Unknown sprite 'ghostt'" in e for e in rec["attempts"][1]["errors"]))
    check("fix prompt contained the test report + code", all(("TEST REPORT" in u and "const game" in u) for k, u in ostate.chat_calls if k.startswith("fix")))
    titles = [d.title for d in rag.load_docs() if d.id in rec["rag"]["hits"]]
    check("coder prompt contained the retrieved RAG patterns", titles and all(any(t in u for k, u in ostate.chat_calls if k == "write") for t in titles), str(titles))
    check("RAG retrieved the falling-objects pattern for the ghost idea", "01-falling-objects" in rec["rag"]["hits"], str(rec["rag"]["hits"]))
    check("plan stage ran once", sum(1 for k, _ in ostate.chat_calls if k == "plan") == 1)
    check("LLM unloaded before art (VRAM hand-off)", ostate.unloads >= 1)
    check("Forge unloaded after art", fstate.unloads == 1)
    check("2 sprites + 1 background requested from Forge", len(fstate.txt2img) == 3, str(len(fstate.txt2img)))
    check("sprite prompt has style prefix", all(p.startswith("pixel art") for w, h, p in fstate.txt2img if "ghost" in p or "pumpkin" in p))
    check("background requested at 4:3-ish size", any(w > h for w, h, _ in fstate.txt2img))
    check("transparent sprites saved", all(__import__("PIL.Image", fromlist=["x"]).open(run_dir / "assets" / f"{n}.png").getpixel((0, 0))[3] == 0 for n in ("ghost", "pumpkin")))
    check("raw diffusion outputs kept for the devlog", (run_dir / "assets" / "raw" / "ghost_raw.png").exists())
    check("single self-contained HTML (no external refs)", not re.search(r'(src|href)="https?://', html) and html.count("data:image/png;base64") >= 3)
    check("AI music embedded and decoded by the browser", "data:audio/wav;base64" in html and rec["music_mode"] == "file", str(rec["music_mode"]))
    check("game reached game over during test", rec["end_state_reached"])
    check("all code versions + plan + run.json + screenshot saved", all((run_dir / f).exists() for f in ("code_v0.js", "code_v1.js", "code_v2.js", "game.js", "plan.json", "run.json", "screenshot.png")))
    check("latest_game.html copy written", (tmp / "latest_game.html").exists())
    print(f"      time: {rec['total_seconds']}s  timings: {rec['timings']}")

    print("\n--- scenario B: --skip-art --no-music, model gets it right first time ---")
    ostate.script = [ms.GOOD_CODE, ms.GOOD_CODE, ms.GOOD_CODE]
    ostate.fix_count = 0
    ostate.chat_calls.clear()
    fstate.txt2img.clear()
    args = Namespace(skip_art=True, no_music=True, music_seconds=3, max_fixes=3, soak=5, open=False)
    rec = harness.run_one("a ghost dodging falling pumpkins", args, r)
    check("passed with 0 fix rounds", rec["passed"] and rec["fix_rounds"] == 0, str(rec["fix_rounds"]))
    check("no Forge calls when art is skipped", not fstate.txt2img)
    check("runtime chiptune fallback used when no music file", rec["music_mode"] == "chiptune", str(rec["music_mode"]))

    print("\n--- scenario C: model never fixes its bug -> pipeline stops after max rounds and reports FAIL ---")
    ostate.script = [ms.BAD_SYNTAX, ms.BAD_SYNTAX, ms.BAD_SYNTAX]
    ostate.fix_count = 0
    args = Namespace(skip_art=True, no_music=True, music_seconds=3, max_fixes=1, soak=3, open=False)
    rec = harness.run_one("a ghost dodging falling pumpkins", args, r)
    check("reports failure honestly", (not rec["passed"]) and rec["fix_rounds"] == 1)

    print("\n--- benchmark table ---")
    p = harness.write_benchmark([rec])
    check("benchmark markdown written", p.exists() and "| 1 |" in p.read_text(encoding="utf-8"))

    osrv.shutdown(); fsrv.shutdown()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed" + (": " + ", ".join(FAILED) if FAILED else ""))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
