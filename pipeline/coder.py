"""Stage 2/4: the local coding LLM writes (and later repairs) the game logic."""
import re

from . import config, llm
from .util import read_text

_SYSTEM_CACHE = {}


def _system():
    if "s" not in _SYSTEM_CACHE:
        _SYSTEM_CACHE["s"] = read_text(config.SKILLS_DIR / "canvas-game.md")
    return _SYSTEM_CACHE["s"]


def _fill(template, **kw):
    for k, v in kw.items():
        template = template.replace(f"${k}$", str(v))
    return template


def build_task(idea, plan, patterns):
    sprites = "\n".join(f"- {s['name']} ({s['width']}x{s['height']}): {s['description']}" for s in plan["sprites"])
    bg = ("A background image exists: draw it first with Sprites.background(ctx)." if plan.get("background")
          else "No background image: Sprites.background(ctx) draws a dark gradient.")
    return _fill(read_text(config.SKILLS_DIR / "coder-task.md"),
                 IDEA=idea, TITLE=plan["title"], RULES=plan["rules"], CONTROLS=plan["controls"],
                 SPRITES=sprites, BACKGROUND_LINE=bg, SFX=", ".join(plan["sfx"]), PATTERNS=patterns or "(none)")


def extract_code(text):
    """Pull the JavaScript out of the model's reply (fenced block, unterminated fence, or full HTML page)."""
    blocks = re.findall(r"```[a-zA-Z]*[ \t]*\n(.*?)```", text, re.S)
    if blocks:
        blocks.sort(key=lambda b: ("game" in b, len(b)), reverse=True)
        return blocks[0].strip("\n")
    m = re.search(r"```[a-zA-Z]*[ \t]*\n(.*)$", text, re.S)           # model ran out of tokens before closing fence
    if m:
        return m.group(1).strip("\n")
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", text, re.S | re.I)
    if scripts:
        return "\n".join(scripts).strip("\n")
    return text.strip("\n") if re.search(r"\b(const|let|var)\s+game\b", text) else None


def validate(code):
    problems = []
    if not code or not code.strip():
        return ["no code found in the reply"]
    if not re.search(r"\b(const|let|var)\s+game\b", code):
        problems.append("the code must define `const game = { over: false, setup() {}, update(dt) {}, draw(ctx) {} };`")
    for fn in ("update", "draw"):
        if not re.search(rf"\b{fn}\s*[(:]", code):
            problems.append(f"game.{fn} is missing")
    return problems


def _ask(messages, label, temperature, retries=2, seed=None):
    tokens, code = 0, None
    for _ in range(retries):
        res = llm.chat(messages, model=config.CODE_MODEL, temperature=temperature, num_predict=4096, label=label, seed=seed)
        tokens += res.tokens
        code = extract_code(res.text)
        problems = validate(code)
        if not problems:
            return code, tokens
        messages = messages + [{"role": "assistant", "content": res.text},
                               {"role": "user", "content": "That reply was not usable: " + "; ".join(problems) +
                                ". Output ONE ```javascript code block with the complete game."}]
    return code or "", tokens


def write_game(idea, plan, patterns):
    msgs = [{"role": "system", "content": _system()}, {"role": "user", "content": build_task(idea, plan, patterns)}]
    return _ask(msgs, "code", 0.2)


def regenerate(idea, plan, patterns, avoid, attempt):
    """Fresh draft with a different random seed and a hotter temperature, told which bug the last draft had.
    Used when repair rounds keep returning the same broken code (a 7B model often 'fixes' by re-printing its input)."""
    import random
    task = build_task(idea, plan, patterns) + (
        "\n\nIMPORTANT: a previous draft of this game crashed with this error:\n" + avoid[:600] +
        "\nWrite the game again from scratch and avoid that bug. Declare every variable at the top level of the code "
        "BEFORE the `const game` object, and only use variables that exist. In draw(ctx) and update(dt) use only names you declared.")
    msgs = [{"role": "system", "content": _system()}, {"role": "user", "content": task}]
    return _ask(msgs, "rewrite", min(0.4 + 0.15 * attempt, 0.8), seed=random.randint(1, 2**31 - 1))


def fix_game(plan, code, report):
    task = _fill(read_text(config.SKILLS_DIR / "fix-task.md"), REPORT=report, CODE=code,
                 SPRITE_NAMES=", ".join(s["name"] for s in plan["sprites"]), SFX=", ".join(plan["sfx"]))
    msgs = [{"role": "system", "content": _system()}, {"role": "user", "content": task}]
    import random
    return _ask(msgs, "fix", 0.3, seed=random.randint(1, 2**31 - 1))
