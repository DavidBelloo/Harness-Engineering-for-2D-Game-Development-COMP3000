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


def torch_gpu():
    """(ok, detail). Runs a real CUDA kernel: a PyTorch build too old for the GPU (e.g. torch < 2.7 on an
    RTX 50-series card) imports fine and even reports CUDA as available, but fails here with
    'no kernel image is available for execution on the device'."""
    try:
        import torch
    except Exception as e:  # noqa: BLE001
        return False, f"PyTorch not installed ({str(e)[:60]}) - run setup.bat"
    if not torch.cuda.is_available():
        build = "CPU-only PyTorch build" if not torch.version.cuda else f"PyTorch {torch.__version__} cannot see a CUDA GPU"
        return False, f"{build} - check the NVIDIA driver, then run setup.bat again"
    try:
        x = torch.ones(8, device="cuda") * 2
        torch.cuda.synchronize()
        assert float(x.sum()) == 16.0
    except Exception as e:  # noqa: BLE001
        return False, (f"PyTorch {torch.__version__} cannot run on {torch.cuda.get_device_name(0)} ({str(e)[:80]}). "
                       "RTX 50-series needs torch >= 2.7 built for CUDA 12.8 - run setup.bat again")
    free, total = torch.cuda.mem_get_info()
    return True, f"PyTorch {torch.__version__} (CUDA {torch.version.cuda}) on {torch.cuda.get_device_name(0)}, {total / 2**30:.0f} GB"


def hf_cached(repo, filename):
    """True if a Hugging Face file is already in the local cache (no network access)."""
    try:
        from huggingface_hub import try_to_load_from_cache
        return isinstance(try_to_load_from_cache(repo, filename), str)
    except Exception:  # noqa: BLE001
        return False


def profile_line():
    gpu = f"{config.GPU_NAME} ({config.GPU_VRAM_MIB / 1024:.0f} GB)" if config.GPU_NAME else "no NVIDIA GPU found"
    img = config.IMAGE_MODEL.split("/")[-1] + (" + " + config.IMAGE_LORA.split("/")[-1] if config.IMAGE_LORA else "")
    if config.IMAGE_BACKEND == "forge":
        img = "Forge @ " + config.FORGE_URL
    return (f"{config.PROFILE} - {gpu} -> code {config.CODE_MODEL}, image {img}, "
            f"music {config.MUSIC_MODEL.split('/')[-1] if config.MUSIC_BACKEND != 'none' else 'chiptune'}")


def run_checks(need_art=True, need_music=True):
    """Returns a list of dicts: name, ok, required, detail."""
    out = []

    def add(name, ok, detail, required=True):
        out.append({"name": name, "ok": bool(ok), "detail": detail, "required": required})

    add("Hardware profile", True, profile_line(), required=False)

    models = llm.list_models()
    add("Ollama server", models is not None, config.OLLAMA_URL if models is not None else
        "not reachable - start the Ollama app (or run.bat starts it), or run `ollama serve`")
    if models is not None:
        ok = llm.has_model(config.CODE_MODEL, models)
        add(f"LLM {config.CODE_MODEL}", ok, "installed" if ok else f"run setup.bat (or: ollama pull {config.CODE_MODEL})")
        ok = llm.has_model(config.EMBED_MODEL, models)
        add(f"Embeddings {config.EMBED_MODEL}", ok,
            "installed" if ok else f"run: ollama pull {config.EMBED_MODEL}  (optional: RAG falls back to keyword search)",
            required=False)

    gpu_needed = (need_art and config.IMAGE_BACKEND != "forge") or (need_music and config.MUSIC_BACKEND != "none")
    if gpu_needed:
        ok, detail = torch_gpu()
        add("PyTorch GPU", ok, detail, required=need_art and config.IMAGE_BACKEND != "forge")

    if need_art:
        ok, detail = sprites.ready()
        if config.IMAGE_BACKEND == "forge":
            add("Forge API", ok, detail)
        else:
            add("Image model (diffusers)", ok, detail)
            if ok:
                cached = hf_cached(config.IMAGE_MODEL, "model_index.json")
                add("Image weights downloaded", cached, "yes" if cached else
                    "not yet - run setup.bat (otherwise they download on the first game, several GB)", required=False)
        try:
            import rembg  # noqa: F401
            add("rembg (background removal)", True, "installed", required=False)
        except Exception:  # noqa: BLE001
            add("rembg (background removal)", False, "run setup.bat  (optional: flood-fill fallback is used)", required=False)

    if need_music and config.MUSIC_BACKEND != "none":
        ok, dev = music.available()
        add("MusicGen (torch + transformers)", ok, f"{config.MUSIC_MODEL} on {dev}" if ok else f"{dev}  (optional: chiptune fallback is used)",
            required=False)
        if ok:
            cached = hf_cached(config.MUSIC_MODEL, "config.json")
            add("Music weights downloaded", cached, "yes" if cached else "not yet - run setup.bat", required=False)

    ok, detail = _browser_ok()
    add("Headless browser (game test)", ok, detail if ok else detail + "  | run: uv run playwright install chromium")
    return out


def print_checks(checks):
    say("Pre-flight checks")
    for c in checks:
        tag = "OK  " if c["ok"] else ("FAIL" if c["required"] else "warn")
        if c["name"] == "Hardware profile":
            tag = "info"
        say(f"  [{tag}] {c['name']}: {c['detail']}")
    return all(c["ok"] or not c["required"] for c in checks)
