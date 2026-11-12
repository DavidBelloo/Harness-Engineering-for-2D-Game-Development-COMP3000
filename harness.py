#!/usr/bin/env python3
"""Prompt in, playable 2D game out - using only local open-source AI.

    python harness.py "a ghost dodging falling pumpkins"
    python harness.py --batch prompts/benchmark.txt

Pipeline (each stage is a separate, swappable module in pipeline/):
    1 plan      local LLM (Ollama)          idea -> JSON design (sprites, sfx, music prompt, rules)
    2 code      RAG + local coding LLM      design + retrieved patterns + skill file -> game logic (JS)
    3 art/music Stable Diffusion Forge + rembg + MusicGen   -> sprites, background, BGM loop
    4 assemble  pipeline/assemble.py        code + assets + runtime -> ONE self-contained HTML file
    5 test/fix  headless browser + LLM      play it, report errors, let the LLM repair its own code
"""
import argparse
import json
import shutil
import sys
import time
import traceback
import webbrowser
from datetime import datetime
from pathlib import Path

from pipeline import assemble, check, coder, config, llm, music, planner, rag, services, sprites
from pipeline.util import say, setup_console, slugify, stage, timed, write_text


def run_one(idea, args, retriever=None):
    t_start = time.time()
    run_dir = config.OUTPUT_DIR / f"{datetime.now():%Y%m%d-%H%M%S}_{slugify(idea, 30)}"
    run_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = run_dir / "assets"
    timings, tokens = {}, {}
    rec = {"idea": idea, "run_dir": str(run_dir), "started": datetime.now().isoformat(timespec="seconds"),
           "models": {"code": config.CODE_MODEL, "plan": config.PLAN_MODEL, "embed": config.EMBED_MODEL,
                      "image": config.FORGE_CHECKPOINT or "(Forge default checkpoint)",
                      "music": config.MUSIC_MODEL if config.MUSIC_BACKEND != "none" and not args.no_music else "none (runtime chiptune)"}}
    say(f"\n######## {idea}")

    # ---- 1. plan --------------------------------------------------------------
    stage("1/5 Plan (local LLM -> JSON design)")
    with timed(timings, "plan"):
        plan, pinfo = planner.make_plan(idea)
    tokens["plan"] = pinfo["tokens"]
    write_text(run_dir / "plan.json", json.dumps(plan, indent=2))
    say(f"  title: {plan['title']}  |  sprites: {', '.join(s['name'] for s in plan['sprites'])}"
        + ("  |  (fallback plan used)" if pinfo["fallback_used"] else ""))
    say(f"  rules: {plan['rules']}")

    # ---- 2. RAG + code ---------------------------------------------------------
    stage("2/5 Retrieve patterns (RAG) + write game code (local coding LLM)")
    with timed(timings, "rag"):
        retriever = retriever or rag.Retriever()
        query = " ".join([idea, plan["rules"]] + [s["description"] for s in plan["sprites"]])
        hits = retriever.search(query, k=config.RAG_TOP_K)
    rec["rag"] = {"method": retriever.method, "hits": [d.id for d, _ in hits]}
    say(f"  retrieved ({retriever.method}): " + ", ".join(d.title for d, _ in hits))
    patterns = rag.format_patterns(hits)
    with timed(timings, "code"):
        code, tokens["code"] = coder.write_game(idea, plan, patterns)
    write_text(run_dir / "code_v0.js", code)

    # ---- 3. assets ---------------------------------------------------------------
    need_art = not args.skip_art
    need_music = config.MUSIC_BACKEND != "none" and not args.no_music
    if need_art or need_music:
        for m in {config.CODE_MODEL, config.PLAN_MODEL}:
            llm.unload(m)                                   # hand the GPU over to image / music models
    stage("3/5 Art (Stable Diffusion + cut-out) and music (MusicGen)")
    sprite_paths, bg_path, art_info = {}, None, {}
    with timed(timings, "art"):
        if need_art:
            sprite_paths, bg_path, art_info = sprites.generate_assets(plan, assets_dir)
            sprites.unload_forge()
        else:
            say("  [art] skipped (--skip-art): coloured placeholder sprites")
            assets_dir.mkdir(parents=True, exist_ok=True)
            for i, s in enumerate(plan["sprites"]):
                p = assets_dir / f"{s['name']}.png"
                sprites.placeholder_sprite(s["name"], s["width"], s["height"], i).save(p)
                sprite_paths[s["name"]] = p
    rec["art"] = art_info
    music_path = None
    with timed(timings, "music"):
        if need_music:
            music_path = music.generate(plan["music"], assets_dir / "music.wav", args.music_seconds)
        else:
            say("  [music] skipped: runtime chiptune will be used")
    rec["music_file"] = bool(music_path)

    # ---- 4/5. assemble, test, fix loop -----------------------------------------------
    stage("4/5 Assemble one HTML file, then 5/5 test in a browser and let the LLM fix its bugs")
    html_path = run_dir / "game.html"
    shot = run_dir / "screenshot.png"
    attempts, result, info = [], None, None
    names = [s["name"] for s in plan["sprites"]]
    for attempt in range(args.max_fixes + 1):
        info = assemble.assemble(code, plan["title"], plan["controls"], sprite_paths, bg_path, music_path, html_path)
        with timed(timings, "test"):
            result = check.run_check(html_path, info, code, planned_sprites=names, planned_sfx=plan["sfx"],
                                     soak_seconds=args.soak, screenshot_path=shot)
        attempts.append({"attempt": attempt, "ok": result.ok, "errors": result.errors, "warnings": result.warnings,
                         "metrics": result.metrics})
        say(f"  test {attempt}: {'PASS' if result.ok else 'FAIL'} ({len(result.errors)} errors, {len(result.warnings)} notes)")
        if result.ok or attempt == args.max_fixes:
            break
        for e in result.errors[:3]:
            say("    - " + e.splitlines()[0][:150])
        say(f"  asking the LLM to fix its code (round {attempt + 1}/{args.max_fixes})")
        first_err = result.errors[0].splitlines()[0] if result.errors else ""
        repeated = bool(attempt >= 1 and attempts[attempt - 1]["errors"] and result.errors
                        and attempts[attempt - 1]["errors"][0].splitlines()[0] == first_err)
        with timed(timings, "fix"):
            if repeated:        # same error again: repairing is not working, so rewrite from scratch with a new seed
                say("  same error as last round -> rewriting the game from scratch with a different seed")
                code, tok = coder.regenerate(idea, plan, patterns, "\n".join(result.errors[0].splitlines()[:6]), attempt)
            else:
                code, tok = coder.fix_game(plan, code, result.report())
        tokens["fix"] = tokens.get("fix", 0) + tok
        write_text(run_dir / f"code_v{attempt + 1}.js", code)

    write_text(run_dir / "game.js", code)
    shutil.copyfile(html_path, config.OUTPUT_DIR / "latest_game.html")
    passed = bool(result and result.ok)
    rec.update({
        "passed": passed, "fix_rounds": len(attempts) - 1, "attempts": attempts,
        "total_seconds": round(time.time() - t_start, 1), "timings": timings, "tokens": tokens,
        "html_bytes": info.size_bytes if info else 0, "plan": plan,
        "end_state_reached": bool(result and result.metrics.get("reached_end_state")),
        "music_mode": result.metrics.get("music_mode") if result else None,
    })
    write_text(run_dir / "run.json", json.dumps(rec, indent=2))
    say(f"\n  {'PASS' if passed else 'FAILED (best effort saved)'} in {rec['total_seconds']}s, "
        f"{rec['fix_rounds']} fix round(s)")
    say(f"  game:  {html_path}")
    say(f"  copy:  {config.OUTPUT_DIR / 'latest_game.html'}")
    if args.open:
        webbrowser.open(html_path.resolve().as_uri())
    return rec


def write_benchmark(recs):
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    lines = ["# Benchmark", "", f"Run: {ts}  |  code model: {config.CODE_MODEL}  |  image: {recs[0]['models']['image'] if recs else ''}",
             "", "| # | Idea | Result | Fix rounds | Total s | Plan s | Code s | Art s | Music s | Test+fix s | Game ends? |",
             "|---|------|--------|-----------:|--------:|-------:|-------:|------:|--------:|-----------:|:----------:|"]
    for i, r in enumerate(recs, 1):
        t = r.get("timings", {})
        res = "PASS" if r.get("passed") else ("ERROR" if r.get("error") else "FAIL")
        lines.append(f"| {i} | {r['idea'][:60]} | {res} | {r.get('fix_rounds', '-')} | {r.get('total_seconds', '-')} | "
                     f"{t.get('plan', '-')} | {t.get('code', '-')} | {t.get('art', '-')} | {t.get('music', '-')} | "
                     f"{round(t.get('test', 0) + t.get('fix', 0), 1) if t else '-'} | {'yes' if r.get('end_state_reached') else 'no'} |")
    ok = sum(1 for r in recs if r.get("passed"))
    lines += ["", f"**{ok}/{len(recs)} prompts produced a game that passed the automated browser test.**"]
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = config.OUTPUT_DIR / f"benchmark_{ts}.md"
    write_text(path, "\n".join(lines) + "\n")
    write_text(config.OUTPUT_DIR / f"benchmark_{ts}.json", json.dumps(recs, indent=2))
    return path


def main():
    setup_console()
    ap = argparse.ArgumentParser(description="Generate a playable 2D game from a plain-English idea (local open-source AI only).")
    ap.add_argument("idea", nargs="?", help="the game idea, in plain English")
    ap.add_argument("--batch", metavar="FILE", help="run every non-empty line of FILE as a separate idea and write a benchmark table")
    ap.add_argument("--skip-art", action="store_true", help="use coloured placeholder sprites (no Forge needed)")
    ap.add_argument("--no-music", action="store_true", help="skip MusicGen (the game uses a built-in chiptune loop)")
    ap.add_argument("--music-seconds", type=int, default=config.MUSIC_SECONDS)
    ap.add_argument("--max-fixes", type=int, default=config.MAX_FIX_ROUNDS, help="max LLM repair rounds after a failed test")
    ap.add_argument("--soak", type=int, default=config.SOAK_SECONDS, help="seconds the browser test plays the game")
    ap.add_argument("--open", action="store_true", help="open the finished game in your browser")
    ap.add_argument("--no-preflight", action="store_true")
    args = ap.parse_args()

    if not args.idea and not args.batch:
        ap.error("give an idea, e.g.  python harness.py \"a ghost dodging falling pumpkins\"")

    if not args.no_preflight:
        checks = services.run_checks(need_art=not args.skip_art, need_music=not args.no_music)
        if not services.print_checks(checks):
            say("\nFix the FAIL items above (see README.md, 'Troubleshooting'), then run again.")
            return 2

    ideas = [args.idea] if args.idea else [ln.strip() for ln in Path(args.batch).read_text(encoding="utf-8").splitlines()
                                           if ln.strip() and not ln.strip().startswith("#")]
    retriever = rag.Retriever()
    recs = []
    for idea in ideas:
        try:
            recs.append(run_one(idea, args, retriever))
        except KeyboardInterrupt:
            raise
        except Exception as e:  # noqa: BLE001
            say(f"\n  ERROR: {e}")
            if "-v" in sys.argv:
                traceback.print_exc()
            recs.append({"idea": idea, "error": str(e)[:300], "models": {"image": config.FORGE_CHECKPOINT or "(Forge default)"}})
    if args.batch:
        path = write_benchmark(recs)
        say(f"\nBenchmark table: {path}")
    return 0 if all(r.get("passed") for r in recs) else 1


if __name__ == "__main__":
    sys.exit(main())
