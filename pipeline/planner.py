"""Stage 1: turn a plain-English idea into a structured game plan (JSON) with the local LLM."""
import json
import re

from . import config, llm
from .util import read_text, snake

KNOWN_SFX = ["hit", "pickup", "jump", "shoot", "explosion", "powerup", "gameover", "win", "click"]


def _parse_json(text):
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:  # noqa: BLE001
            return None
    return None


def _int(v, default, lo, hi):
    try:
        return max(lo, min(hi, int(float(v))))
    except (TypeError, ValueError):
        return default


UI_NAMES = {"score", "lives", "life", "health", "hud", "ui", "text", "counter", "timer", "button", "title", "gameover", "game_over"}


def normalise(raw, idea):
    """Validate/repair whatever the small model produced so later stages can rely on the shape."""
    raw = raw if isinstance(raw, dict) else {}
    title = str(raw.get("title") or idea).strip()[:40] or "Untitled Game"
    plan = {
        "idea": idea,
        "title": title,
        "controls": str(raw.get("controls") or "Arrow keys move, Space acts").strip()[:80],
        "rules": str(raw.get("rules") or f"{idea}. Score points and avoid danger. You lose when you run out of lives.").strip()[:500],
        "background": str(raw.get("background") or "").strip()[:80],
        "music": str(raw.get("music") or f"upbeat 8-bit chiptune loop, {title}").strip()[:120],
    }
    sprites, used = [], set()
    for i, s in enumerate(raw.get("sprites") or []):
        if isinstance(s, str):
            s = {"name": s, "description": s}
        if not isinstance(s, dict):
            continue
        desc = str(s.get("description") or s.get("name") or "").strip()[:100]
        name = snake(s.get("name") or desc or f"sprite{i + 1}")
        if sprites and name in UI_NAMES:      # a 7B model sometimes plans "score"/"lives" pictures: never drawable, drop them
            continue
        if not desc or name in used or name.startswith("__"):
            continue
        used.add(name)
        default_size = 64 if not sprites else 48
        sprites.append({"name": name, "description": desc,
                        "width": _int(s.get("width"), default_size, 16, 128),
                        "height": _int(s.get("height"), default_size, 16, 128)})
        if len(sprites) == 6:
            break
    if not sprites:
        sprites = [{"name": "player", "description": idea[:80], "width": 64, "height": 64},
                   {"name": "hazard", "description": "a dangerous obstacle", "width": 48, "height": 48}]
    plan["sprites"] = sprites
    sfx = [s for s in dict.fromkeys(str(x).lower() for x in (raw.get("sfx") or [])) if s in KNOWN_SFX]
    for must in ("hit", "gameover"):
        if must not in sfx:
            sfx.append(must)
    plan["sfx"] = sfx
    return plan


def make_plan(idea, retries=3):
    system = read_text(config.SKILLS_DIR / "planner.md")
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": f'Game idea: "{idea}"'}]
    tokens, attempts, raw = 0, 0, None
    for attempt in range(retries):
        attempts += 1
        res = llm.chat(messages, model=config.PLAN_MODEL, json_mode=True, temperature=0.6 if attempt == 0 else 0.3,
                       num_predict=900, label="plan")
        tokens += res.tokens
        raw = _parse_json(res.text)
        if isinstance(raw, dict) and raw.get("sprites"):
            break
        raw = None
    return normalise(raw, idea), {"attempts": attempts, "tokens": tokens, "fallback_used": raw is None}
