"""Central configuration.

Every value can be overridden with an environment variable, so the same repo runs
on a dev PC and on a lab machine without code changes (this is the portability story:
paths, URLs and model names are configuration, never hard-coded).
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"
DOCS_DIR = ROOT / "docs"
OUTPUT_DIR = Path(os.environ.get("HARNESS_OUTPUT", str(ROOT / "output")))
CACHE_DIR = ROOT / ".cache"


def _env(name, default):
    return os.environ.get(name, default)


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _env_bool(name, default):
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


# ---- LLM (Ollama) ---------------------------------------------------------
OLLAMA_URL = _env("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
CODE_MODEL = _env("HARNESS_CODE_MODEL", "qwen2.5-coder:7b")
PLAN_MODEL = _env("HARNESS_PLAN_MODEL", CODE_MODEL)
EMBED_MODEL = _env("HARNESS_EMBED_MODEL", "nomic-embed-text")
NUM_CTX = _env_int("HARNESS_NUM_CTX", 8192)

# ---- Image generation (Stable Diffusion Forge, started with --api) --------
FORGE_URL = _env("FORGE_URL", "http://127.0.0.1:7860").rstrip("/")
FORGE_DIR = _env("FORGE_DIR", "")            # only used by setup_check.py --enable-forge-api
FORGE_CHECKPOINT = _env("FORGE_CHECKPOINT", "")  # empty = whatever model Forge has loaded
FORGE_LORA = _env("FORGE_LORA", "")          # e.g. "pixel_art_xl:0.8" (optional)
FORGE_STEPS = _env_int("FORGE_STEPS", 20)
FORGE_CFG = float(_env("FORGE_CFG", "7"))
FORGE_SAMPLER = _env("FORGE_SAMPLER", "Euler a")
FORGE_TIMEOUT = _env_int("FORGE_TIMEOUT", 300)
SPRITE_GEN_SIZE = _env_int("FORGE_SPRITE_SIZE", 512)      # 512 for SD1.5, 1024 for SDXL
BG_GEN_SIZE = (SPRITE_GEN_SIZE, SPRITE_GEN_SIZE * 3 // 4 // 64 * 64)  # 4:3-ish, multiple of 64
UNLOAD_FORGE = _env_bool("HARNESS_UNLOAD_FORGE", True)

SPRITE_PROMPT_PREFIX = "pixel art, game sprite, single object, centered, full body, flat colors, plain white background, "
SPRITE_NEGATIVE = ("text, watermark, signature, multiple objects, cropped, blurry, photo, realistic, "
                   "scenery, landscape, border, frame, shadow on ground")
BG_PROMPT_SUFFIX = ", pixel art, 2d game background, wide scenery, no characters, no text"
BG_NEGATIVE = "text, watermark, characters, people, ui, frame, blurry"

# ---- Sprite post-processing ------------------------------------------------
REMBG_MODEL = _env("HARNESS_REMBG_MODEL", "u2net")
PIXEL_GRID = _env_int("HARNESS_PIXEL_GRID", 32)   # logical pixels per sprite side; 0 disables pixelation
PALETTE_COLORS = _env_int("HARNESS_PALETTE", 24)  # 0 disables colour quantisation
BG_GRID = (200, 150)                               # background logical resolution

# ---- Music (MusicGen via transformers) -------------------------------------
MUSIC_BACKEND = _env("HARNESS_MUSIC", "musicgen")   # musicgen | none
MUSIC_MODEL = _env("HARNESS_MUSIC_MODEL", "facebook/musicgen-small")
MUSIC_SECONDS = _env_int("HARNESS_MUSIC_SECONDS", 15)

# ---- Game / loop -----------------------------------------------------------
CANVAS_W, CANVAS_H = 800, 600
MAX_FIX_ROUNDS = _env_int("HARNESS_MAX_FIXES", 3)
RAG_TOP_K = _env_int("HARNESS_RAG_K", 3)
SOAK_SECONDS = _env_int("HARNESS_SOAK", 10)          # how long the test plays the game
