"""Bundle LLM-written game code + generated assets into ONE self-contained HTML file."""
import base64
import html
import json
from dataclasses import dataclass
from pathlib import Path

from . import config
from .util import read_text, write_text

TEMPLATE = Path(__file__).with_name("template.html")
RUNTIME = config.SKILLS_DIR / "runtime-helpers.js"


@dataclass
class AssembleInfo:
    html_path: Path
    game_start_line: int   # 1-based line in the HTML where the LLM's code begins
    game_line_count: int
    size_bytes: int


def _data_uri(path, mime):
    return f"data:{mime};base64," + base64.b64encode(Path(path).read_bytes()).decode("ascii")


def assemble(code, title, controls, sprite_paths, background_path, music_path, out_html):
    """sprite_paths: {name: png path}. background_path / music_path may be None."""
    assets = {
        "title": title,
        "controls": controls or "",
        "sprites": {name: _data_uri(p, "image/png") for name, p in sprite_paths.items()},
        "background": _data_uri(background_path, "image/png") if background_path else None,
        "music": _data_uri(music_path, "audio/wav") if music_path else None,
    }
    assets_json = json.dumps(assets).replace("</", "<\\/")

    template = read_text(TEMPLATE)
    head, tail = template.split("{{GAME_CODE}}")
    head = (head.replace("{{TITLE}}", html.escape(title or "Game"))
                .replace("{{ASSETS_JSON}}", assets_json)
                .replace("{{RUNTIME}}", read_text(RUNTIME)))
    safe_code = code.replace("</script", "<\\/script").strip("\n")
    start_line = head.count("\n") + 1
    page = head + safe_code + tail

    write_text(out_html, page)
    return AssembleInfo(Path(out_html), start_line, safe_code.count("\n") + 1, len(page.encode("utf-8")))


def info_from_html(html_path, code):
    """Recover the line offsets of the LLM code inside an assembled page (used by the MCP test tool)."""
    lines = Path(html_path).read_text(encoding="utf-8").split("\n")
    for i, ln in enumerate(lines):
        if ln.startswith("window.__game = (function"):
            return AssembleInfo(Path(html_path), i + 2, code.count("\n") + 1, Path(html_path).stat().st_size)
    return None
