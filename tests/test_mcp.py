"""Drives mcp_server.py through a real MCP client over stdio, with a mock Forge server standing in for Stable Diffusion.

    python tests/test_mcp.py
"""
import asyncio
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import mock_servers as ms  # noqa: E402
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"  [{'ok' if cond else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not cond else ""))


def text(res):
    return "".join(c.text for c in res.content if getattr(c, "type", "") == "text")


async def main():
    tmp = Path(tempfile.mkdtemp(prefix="harness_mcp_"))
    fstate = ms.State()
    fsrv, fport = ms.start(ms.make_handler_forge, fstate)
    env = dict(os.environ, FORGE_URL=f"http://127.0.0.1:{fport}", OLLAMA_URL="http://127.0.0.1:9", PYTHONIOENCODING="utf-8")
    params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "mcp_server.py")], env=env, cwd=str(ROOT))
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = {t.name for t in (await s.list_tools()).tools}
            check("server exposes the 7 harness tools", tools == {"list_runtime_api", "search_game_docs", "generate_sprite", "generate_background",
                                                                   "generate_music", "assemble_game", "test_game"}, str(tools))
            api = text(await s.call_tool("list_runtime_api", {}))
            check("list_runtime_api returns the skill file", "Sprites.draw" in api and "```javascript example" in api)
            docs = text(await s.call_tool("search_game_docs", {"query": "shoot asteroids with a rocket", "k": 3}))
            check("search_game_docs (RAG, keyword fallback: Ollama is down) returns the shooter pattern", "Shooter" in docs)

            out = tmp / "out"
            for name, desc in (("ghost", "cute white ghost"), ("pumpkin", "orange pumpkin")):
                res = json.loads(text(await s.call_tool("generate_sprite", {"name": name, "description": desc, "width": 64, "height": 64, "out_dir": str(out)})))
                check(f"generate_sprite({name}) wrote a PNG", Path(res["path"]).exists() and res["cutout"] in ("rembg", "floodfill"), str(res))
            music = text(await s.call_tool("generate_music", {"prompt": "spooky", "seconds": 5, "out_path": str(out / "music.wav")}))
            check("generate_music degrades gracefully with no MusicGen", "chiptune" in music or Path(music).exists(), music)

            code = ms.GOOD_CODE
            (out / "game.js").write_text(code, encoding="utf-8")
            res = json.loads(text(await s.call_tool("assemble_game", {"game_js_path": str(out / "game.js"), "title": "Ghost Dodger",
                                                                    "sprites_dir": str(out), "out_html": str(out / "game.html")})))
            check("assemble_game built one HTML with both sprites", Path(res["html"]).exists() and res["sprites"] == ["ghost", "pumpkin"], str(res))
            rep = text(await s.call_tool("test_game", {"html_path": str(out / "game.html"), "game_js_path": str(out / "game.js"),
                                                       "sprite_names": "ghost,pumpkin", "soak_seconds": 8}))
            check("test_game: good code -> PASS", rep.startswith("PASS"), rep[:300])

            (out / "bad.js").write_text(ms.BAD_SYNTAX, encoding="utf-8")
            await s.call_tool("assemble_game", {"game_js_path": str(out / "bad.js"), "title": "Bad", "sprites_dir": str(out), "out_html": str(out / "bad.html")})
            rep = text(await s.call_tool("test_game", {"html_path": str(out / "bad.html"), "game_js_path": str(out / "bad.js"), "sprite_names": "ghost,pumpkin", "soak_seconds": 3}))
            check("test_game: syntax error -> FAIL with the offending line", rep.startswith("FAIL") and "SyntaxError" in rep and ">>" in rep, rep[:400])
    fsrv.shutdown()
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed" + (": " + ", ".join(FAILED) if FAILED else ""))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
