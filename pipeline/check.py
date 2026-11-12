"""Automated browser test for a generated game.

Opens the assembled HTML in a headless browser, plays it with scripted + random input
and reports (a) JavaScript errors with the offending line of the LLM's code, and
(b) behavioural problems: frozen/blank canvas, sprites never drawn, game never ends.
The report text is fed straight back to the coding LLM in the fix loop.
"""
import os
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

SNAPSHOT_JS = """() => {
  const c = document.getElementById('c');
  const t = document.createElement('canvas'); t.width = 40; t.height = 30;
  const x = t.getContext('2d'); x.drawImage(c, 0, 0, 40, 30);
  const d = x.getImageData(0, 0, 40, 30).data;
  const colors = new Set(); let h = 0;
  for (let i = 0; i < d.length; i += 4) {
    const k = ((d[i] >> 4) << 8) | ((d[i + 1] >> 4) << 4) | (d[i + 2] >> 4);
    colors.add(k); h = (h * 31 + k) >>> 0;
  }
  const H = window.__harness || {};
  return { hash: h, colors: colors.size, frames: H.frames || 0, over: !!H.over, won: !!H.won, crashed: !!H.crashed };
}"""

CHROME_ARGS = ["--autoplay-policy=no-user-gesture-required", "--mute-audio"]


@dataclass
class CheckResult:
    ok: bool
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    screenshot: str = ""

    def report(self):
        lines = []
        for e in self.errors:
            lines.append("- ERROR: " + e)
        for w in self.warnings:
            lines.append("- note: " + w)
        return "\n".join(lines) if lines else "(no problems found)"


def _launch(p):
    """Try bundled Chromium, then Microsoft Edge, then Chrome (Edge ships with every Windows PC)."""
    args = list(CHROME_ARGS)
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        args.append("--no-sandbox")
    exe = os.environ.get("HARNESS_BROWSER_PATH")
    attempts = []
    if exe:
        attempts.append(("custom", dict(executable_path=exe)))
    attempts += [("chromium", {}), ("msedge", dict(channel="msedge")), ("chrome", dict(channel="chrome"))]
    errs = []
    for name, kw in attempts:
        try:
            return p.chromium.launch(headless=True, args=args, **kw)
        except Exception as e:  # noqa: BLE001
            errs.append(f"{name}: {str(e).splitlines()[0][:100]}")
    raise RuntimeError("No usable browser for the game test. Run `playwright install chromium`. Tried: " + "; ".join(errs))


def _map_lines(text, info):
    """Find 'file.html:LINE:COL' in an error text and map it to a line of the LLM's code."""
    if not info:
        return None
    for m in re.finditer(r":(\d+):(\d+)", text):
        line = int(m.group(1))
        rel = line - info.game_start_line + 1
        if 1 <= rel <= info.game_line_count:
            return rel
    return None


def _clean(text):
    """Drop stack-trace noise (file paths) and repeated first lines so the report stays short for a small LLM."""
    lines = [ln for ln in str(text).splitlines() if not re.match(r"\s+at ", ln)]
    if len(lines) > 1 and lines[1].strip() and lines[1].strip() in lines[0]:
        lines.pop(1)
    return "\n".join(lines).strip()


def _context(code_lines, rel, radius=2):
    lo, hi = max(1, rel - radius), min(len(code_lines), rel + radius)
    out = []
    for n in range(lo, hi + 1):
        out.append(f"{'>>' if n == rel else '  '} {n:3d} | {code_lines[n - 1]}")
    return "\n".join(out)


def run_check(html_path, info=None, code=None, planned_sprites=(), planned_sfx=(), soak_seconds=10,
              screenshot_path=None):
    from playwright.sync_api import sync_playwright

    code_lines = (code or "").split("\n")
    raw_errors, raw_warnings, cdp_errors = [], [], []
    metrics = {}
    shot = ""

    with sync_playwright() as p:
        browser = _launch(p)
        try:
            ctx = browser.new_context(viewport={"width": 900, "height": 700})
            page = ctx.new_page()
            try:
                cdp = ctx.new_cdp_session(page)
                cdp.send("Runtime.enable")

                def on_exc(ev):
                    d = ev.get("exceptionDetails", {})
                    desc = (d.get("exception") or {}).get("description") or d.get("text", "exception")
                    cdp_errors.append((desc, d.get("lineNumber")))
                cdp.on("Runtime.exceptionThrown", on_exc)
            except Exception:  # noqa: BLE001
                pass
            page.on("pageerror", lambda e: raw_errors.append(("pageerror", str(e), None)))
            page.on("console", lambda m: (raw_errors if m.type == "error" else raw_warnings).append(("console", m.text, None))
                    if m.type in ("error", "warning") else None)

            page.goto(Path(html_path).resolve().as_uri())
            try:
                page.wait_for_function("window.__harness && window.__harness.ready", timeout=20000)
            except Exception:  # noqa: BLE001
                raw_errors.append(("check", "Game never finished loading (assets or setup() hung).", None))

            snaps = [page.evaluate(SNAPSHOT_JS)]
            page.keyboard.press("Enter")           # dismiss splash / satisfy audio autoplay rules
            page.wait_for_timeout(400)
            snaps.append(page.evaluate(SNAPSHOT_JS))

            script = [("ArrowLeft", 600), ("ArrowRight", 900), ("ArrowUp", 400), ("ArrowDown", 400),
                      ("a", 300), ("d", 300), ("Space", 150), ("Space", 150)]
            for key, ms in script:
                page.keyboard.down(key)
                page.wait_for_timeout(ms)
                page.keyboard.up(key)
                snaps.append(page.evaluate(SNAPSHOT_JS))
            page.mouse.click(450, 350)
            page.wait_for_timeout(300)
            if screenshot_path:
                page.screenshot(path=str(screenshot_path))
                shot = str(screenshot_path)

            # Soak: first half idle, second half random input; stop early if the game ends.
            reached_end, won, t0 = False, False, time.time()
            rng = random.Random(7)
            keys = ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Space"]
            while time.time() - t0 < soak_seconds:
                s = page.evaluate(SNAPSHOT_JS)
                snaps.append(s)
                if s["crashed"]:
                    break
                if s["over"]:
                    reached_end, won = True, s["won"]
                    break
                if time.time() - t0 > soak_seconds / 2:
                    k = rng.choice(keys)
                    page.keyboard.down(k)
                    page.wait_for_timeout(rng.randint(80, 350))
                    page.keyboard.up(k)
                else:
                    page.wait_for_timeout(250)
            if reached_end and screenshot_path:
                end_shot = Path(str(screenshot_path).replace(".png", "_end.png"))
                page.screenshot(path=str(end_shot))

            final = page.evaluate("() => JSON.stringify(window.__harness || {})")
            import json as _json
            harness_state = _json.loads(final)
        finally:
            browser.close()

    # ---- assemble the verdict ------------------------------------------------
    errors, warnings = [], []

    def add_error(raw, line0=None):
        rel = None
        if line0 is not None and info:                      # CDP gives an exact 0-based document line
            cand = line0 + 1 - info.game_start_line + 1
            if 1 <= cand <= info.game_line_count:
                rel = cand
        if rel is None:
            rel = _map_lines(raw, info)                     # otherwise parse the stack trace
        msg = _clean(raw)
        # skip duplicates (the same error is reported by several channels)
        if any(msg in e or e.split("\n")[0] in msg for e in errors):
            return
        if rel and code_lines:
            msg += f"\n  at line {rel} of your code:\n{_context(code_lines, rel)}"
        errors.append(msg)

    for desc, line0 in cdp_errors:
        add_error(desc, line0)
    for _, text, _ in raw_errors:
        add_error(text)
    if len(errors) > 1:                                     # secondary symptom of a load/syntax error
        errors = [e for e in errors if not e.startswith("Game code must define")] or errors
    for _, text, _ in raw_warnings:
        warnings.append(text[:200])

    frames = max(s["frames"] for s in snaps)
    colors = max(s["colors"] for s in snaps)
    hashes = {s["hash"] for s in snaps[1:]}
    if not any("Game code must define" in e for e in errors):
        if frames < 30 and not harness_state.get("crashed"):
            errors.append(f"The game loop barely ran (only {frames} frames). Make sure update() and draw() do not hang.")
        if colors < 3 and not harness_state.get("crashed"):
            errors.append("The canvas looks blank (almost no colours). Draw the background and every object each frame in draw(ctx).")
        elif len(hashes) < 5 and not harness_state.get("crashed"):
            errors.append(f"Almost nothing on screen changed while keys were pressed and time passed (only {len(hashes)} "
                          "different frames) - the game looks frozen. Objects must move in update(dt) and the player must react to Input.")
    draws = harness_state.get("spriteDraws", {}) or {}
    if planned_sprites and not harness_state.get("crashed"):
        if sum(draws.values()) == 0:
            errors.append("None of the generated sprites were ever drawn. Use Sprites.draw(ctx, 'name', x, y, w, h) for every object. "
                          "Sprite names: " + ", ".join(planned_sprites))
        else:
            unused = [n for n in planned_sprites if n not in draws]
            if unused:
                errors.append("These sprites were never drawn during the test: " + ", ".join(unused) + ". Spawn/draw every one of them "
                              "with Sprites.draw(ctx, 'name', x, y, w, h) soon after the game starts (for example, create the first object in setup()).")
    sfx = harness_state.get("sfxPlays", {}) or {}
    if planned_sfx and not sfx:
        warnings.append("No sound effect was played during the test.")
    if not reached_end:
        warnings.append(f"The game did not reach game over / win within {soak_seconds}s of idle + random input "
                        "(make sure the lose condition is reachable).")

    metrics = {
        "frames": frames, "colors_seen": colors, "distinct_frames": len(hashes),
        "reached_end_state": reached_end, "won": won, "sprite_draws": draws, "sfx_plays": sfx,
        "music_mode": harness_state.get("musicMode"), "crashed": bool(harness_state.get("crashed")),
    }
    return CheckResult(ok=not errors, errors=errors, warnings=warnings, metrics=metrics, screenshot=shot)
