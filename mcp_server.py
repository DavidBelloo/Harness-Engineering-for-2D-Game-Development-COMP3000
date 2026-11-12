#!/usr/bin/env python3
"""MCP server: the harness's tools, exposed over the Model Context Protocol (stdio).

harness.py runs these same pipeline modules as a fixed, reliable pipeline. This server exposes them
as MCP tools so ANY MCP-capable agent (OpenCode, Goose, Cline, ... driving a local model) can orchestrate
them itself - the "agentic" mode of the same harness.

    python mcp_server.py        # speaks MCP on stdin/stdout; progress logs go to stderr

Example client config (Claude-Desktop-style JSON used by most MCP clients):
    {"mcpServers": {"game-harness": {"command": "python", "args": ["C:/path/to/harness-repo/mcp_server.py"]}}}
"""
import asyncio
import json
from pathlib import Path

from pipeline import util

util.redirect_to_stderr()          # stdout carries the protocol: never print there

from mcp.server.fastmcp import FastMCP  # noqa: E402

from pipeline import assemble, check, config, music, rag, sprites  # noqa: E402
from pipeline.util import read_text, snake  # noqa: E402

mcp = FastMCP("game-harness")
_retriever = {}


def _out(p):
    p = Path(p)
    return p if p.is_absolute() else config.ROOT / p


@mcp.tool()
def list_runtime_api() -> str:
    """Return the skill file: rules, the full runtime API (Input, Sprites, SFX, Anim, Particles...) and a worked example game.
    Read this BEFORE writing game code."""
    return read_text(config.SKILLS_DIR / "canvas-game.md")


@mcp.tool()
def search_game_docs(query: str, k: int = 3) -> str:
    """RAG: search the knowledge base of game-making patterns (falling objects, shooter, platformer, grid/snake, mouse games...)
    and return the best-matching pattern documents with code that uses the runtime API."""
    if "r" not in _retriever:
        _retriever["r"] = rag.Retriever()
    return rag.format_patterns(_retriever["r"].search(query, k=max(1, min(int(k), 6))))


@mcp.tool()
async def generate_sprite(name: str, description: str, width: int = 64, height: int = 64, out_dir: str = "output/mcp") -> str:
    """Generate one transparent pixel-art sprite with local Stable Diffusion (Forge must be running with --api).
    Describe ONE object in 3-8 words. Returns the PNG path; use the same `name` in Sprites.draw(ctx, name, ...)."""
    w, h = max(16, min(int(width), 128)), max(16, min(int(height), 128))

    def work():
        if not sprites.forge_up():
            raise RuntimeError(sprites.FORGE_HELP.format(url=config.FORGE_URL))
        img, raw, meta = sprites.make_sprite(description, w, h)
        d = _out(out_dir)
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{snake(name)}.png"
        img.save(path)
        return json.dumps({"path": str(path), "width": w, "height": h, **meta})
    return await asyncio.to_thread(work)


@mcp.tool()
async def generate_background(description: str, out_path: str = "output/mcp/background.png") -> str:
    """Generate an 800x600 pixel-art background (scenery only, no characters)."""
    def work():
        if not sprites.forge_up():
            raise RuntimeError(sprites.FORGE_HELP.format(url=config.FORGE_URL))
        img, raw, meta = sprites.make_background(description)
        p = _out(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        img.save(p)
        return json.dumps({"path": str(p), **meta})
    return await asyncio.to_thread(work)


@mcp.tool()
async def generate_music(prompt: str, seconds: int = 15, out_path: str = "output/mcp/music.wav") -> str:
    """Generate a looping background-music WAV with MusicGen. If unavailable, returns 'unavailable' and the game
    automatically uses a built-in chiptune loop instead."""
    def work():
        p = music.generate(prompt, _out(out_path), max(5, min(int(seconds), 30)))
        return str(p) if p else "unavailable: the runtime chiptune loop will be used"
    return await asyncio.to_thread(work)


@mcp.tool()
def assemble_game(game_js_path: str, title: str, sprites_dir: str, out_html: str = "output/mcp/game.html",
                  controls: str = "", background_path: str = "", music_path: str = "") -> str:
    """Bundle the game code (a .js file defining `const game`), every PNG in sprites_dir (file name = sprite name),
    an optional background and music into ONE self-contained HTML file. Returns the html path."""
    code = read_text(_out(game_js_path))
    sprite_paths = {p.stem: p for p in sorted(_out(sprites_dir).glob("*.png")) if p.stem not in ("background",)}
    bg = _out(background_path) if background_path else None
    mu = _out(music_path) if music_path else None
    info = assemble.assemble(code, title, controls, sprite_paths, bg if bg and bg.exists() else None,
                             mu if mu and mu.exists() else None, _out(out_html))
    return json.dumps({"html": str(info.html_path), "bytes": info.size_bytes, "sprites": sorted(sprite_paths)})


@mcp.tool()
async def test_game(html_path: str, game_js_path: str, sprite_names: str = "", soak_seconds: int = 8) -> str:
    """Play the game in a headless browser (scripted + random input) and return a report: JavaScript errors WITH the
    offending line of your code, frozen/blank canvas, sprites never drawn, whether the game can end.
    Starts with PASS or FAIL. If FAIL, fix the code and call assemble_game + test_game again."""
    def work():
        code = read_text(_out(game_js_path))
        html = _out(html_path)
        info = assemble.info_from_html(html, code)
        names = [n.strip() for n in sprite_names.split(",") if n.strip()]
        res = check.run_check(html, info, code, planned_sprites=names, planned_sfx=(), soak_seconds=int(soak_seconds),
                              screenshot_path=html.with_suffix(".png"))
        return ("PASS\n" if res.ok else "FAIL\n") + res.report() + "\nmetrics: " + json.dumps(res.metrics)
    return await asyncio.to_thread(work)    # Playwright's sync API must not run inside the server's event loop


if __name__ == "__main__":
    mcp.run()
