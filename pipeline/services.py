"""Pre-flight checks: is every tool the pipeline depends on actually available?"""
from . import config, llm, music, sprites
from .util import say


def _browser_ok():
    try:
        from playwright.sync_api import sync_playwright
        from .check import _launch
        with sync_playwright() as p:
            b = _launch(p)
            v = b.version
            b.close()
        return True, f"browser {v}"
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:140]


def run_checks(need_art=True, need_music=True):
    """Returns a list of dicts: name, ok, required, detail."""
    out = []

    def add(name, ok, detail, required=True):
        out.append({"name": name, "ok": bool(ok), "detail": detail, "required": required})

    models = llm.list_models()
    add("Ollama server", models is not None, config.OLLAMA_URL if models is not None else
        "not reachable - start the Ollama app or run `ollama serve`")
    if models is not None:
        ok = llm.has_model(config.CODE_MODEL, models)
        add(f"LLM {config.CODE_MODEL}", ok, "installed" if ok else f"run: ollama pull {config.CODE_MODEL}")
        ok = llm.has_model(config.EMBED_MODEL, models)
        add(f"Embeddings {config.EMBED_MODEL}", ok,
            "installed" if ok else f"run: ollama pull {config.EMBED_MODEL}  (optional: RAG falls back to keyword search)",
            required=False)
    if need_art:
        up = sprites.forge_up()
        add("Forge API", up, config.FORGE_URL if up else "not reachable - start Forge with --api (python setup_check.py --enable-forge-api)")
        try:
            import rembg  # noqa: F401
            add("rembg (background removal)", True, "installed", required=False)
        except Exception:  # noqa: BLE001
            add("rembg (background removal)", False, "pip install rembg onnxruntime  (optional: flood-fill fallback is used)", required=False)
    if need_music and config.MUSIC_BACKEND != "none":
        ok, dev = music.available()
        add("MusicGen (torch + transformers)", ok, f"device: {dev}" if ok else f"{dev}  (optional: chiptune fallback is used)", required=False)
        if ok and dev == "cpu":
            add("MusicGen GPU", False, "PyTorch cannot see your GPU (CPU-only build?) - music would take minutes", required=False)
    ok, detail = _browser_ok()
    add("Headless browser (game test)", ok, detail if ok else detail + "  | run: playwright install chromium")
    return out


def print_checks(checks):
    say("Pre-flight checks")
    for c in checks:
        tag = "OK  " if c["ok"] else ("FAIL" if c["required"] else "warn")
        say(f"  [{tag}] {c['name']}: {c['detail']}")
    return all(c["ok"] or not c["required"] for c in checks)
