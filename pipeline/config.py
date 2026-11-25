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


# ---- Hardware profile ------------------------------------------------------
# One repo, two machines: the model sizes are picked from the GPU's memory so the same code runs on
# an 8 GB dev PC and a 16 GB lab machine. Override with HARNESS_PROFILE=high|low.
def _gpu_info():
    """(name, total MiB) of the first NVIDIA GPU via nvidia-smi (no torch import needed), or (None, 0)."""
    import shutil
    import subprocess
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None, 0
    try:
        out = subprocess.run([exe, "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10).stdout.strip().splitlines()
        name, mem = [x.strip() for x in out[0].split(",")[:2]]
        return name, int(float(mem))
    except Exception:  # noqa: BLE001
        return None, 0


PROFILES = {
    # >= 14 GB VRAM (RTX 5080 16 GB, 4080, 4090 ...)
    "high": {
        "code_model": "qwen2.5-coder:14b",
        "image_model": "stabilityai/stable-diffusion-xl-base-1.0",
        "image_vae": "madebyollin/sdxl-vae-fp16-fix",       # stock SDXL VAE produces black/NaN images in fp16
        "image_lora": "nerijs/pixel-art-xl",
        "image_lora_file": "pixel-art-xl.safetensors",
        "image_size": 1024,
        "image_steps": 25,
        "music_model": "facebook/musicgen-medium",
    },
    # 8-12 GB VRAM (RTX 4060 8 GB ...)
    "low": {
        "code_model": "qwen2.5-coder:7b",
        "image_model": "stable-diffusion-v1-5/stable-diffusion-v1-5",
        "image_vae": "",
        "image_lora": "",
        "image_lora_file": "",
        "image_size": 512,
        "image_steps": 20,
        "music_model": "facebook/musicgen-small",
    },
}
HIGH_VRAM_MIB = 14000

GPU_NAME, GPU_VRAM_MIB = _gpu_info()
PROFILE = _env("HARNESS_PROFILE", "high" if GPU_VRAM_MIB >= HIGH_VRAM_MIB else "low").lower()
if PROFILE not in PROFILES:
    PROFILE = "low"
_P = PROFILES[PROFILE]

# ---- LLM (Ollama) ---------------------------------------------------------
OLLAMA_URL = _env("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
CODE_MODEL = _env("HARNESS_CODE_MODEL", _P["code_model"])
PLAN_MODEL = _env("HARNESS_PLAN_MODEL", CODE_MODEL)
EMBED_MODEL = _env("HARNESS_EMBED_MODEL", "nomic-embed-text")
NUM_CTX = _env_int("HARNESS_NUM_CTX", 8192)

# ---- Image generation ------------------------------------------------------
# "diffusers" (default): Stable Diffusion runs inside the harness's own Python process - nothing else to
#                        install or start; weights download from Hugging Face on first use.
# "forge":               the older setup - an external Stable Diffusion Forge started with --api.
IMAGE_BACKEND = _env("HARNESS_IMAGE_BACKEND", "diffusers").lower()
IMAGE_MODEL = _env("HARNESS_IMAGE_MODEL", _P["image_model"])
IMAGE_VAE = _env("HARNESS_IMAGE_VAE", _P["image_vae"])
IMAGE_LORA = _env("HARNESS_IMAGE_LORA", _P["image_lora"])               # Hugging Face repo id, or "" for none
IMAGE_LORA_FILE = _env("HARNESS_IMAGE_LORA_FILE", _P["image_lora_file"])
IMAGE_LORA_SCALE = float(_env("HARNESS_IMAGE_LORA_SCALE", "1.1"))
IMAGE_STEPS = _env_int("HARNESS_IMAGE_STEPS", _P["image_steps"])
IMAGE_CFG = float(_env("HARNESS_IMAGE_CFG", "7"))
SPRITE_GEN_SIZE = _env_int("HARNESS_IMAGE_SIZE", _P["image_size"])     # 512 for SD1.5, 1024 for SDXL
BG_GEN_SIZE = (SPRITE_GEN_SIZE, SPRITE_GEN_SIZE * 3 // 4 // 64 * 64)    # 4:3-ish, multiple of 64

# Forge backend only (HARNESS_IMAGE_BACKEND=forge)
FORGE_URL = _env("FORGE_URL", "http://127.0.0.1:7860").rstrip("/")
FORGE_DIR = _env("FORGE_DIR", "")            # only used by setup_check.py --enable-forge-api
FORGE_CHECKPOINT = _env("FORGE_CHECKPOINT", "")  # empty = whatever model Forge has loaded
FORGE_LORA = _env("FORGE_LORA", "")          # e.g. "pixel_art_xl:0.8" (optional)
FORGE_SAMPLER = _env("FORGE_SAMPLER", "Euler a")
FORGE_TIMEOUT = _env_int("FORGE_TIMEOUT", 300)
UNLOAD_FORGE = _env_bool("HARNESS_UNLOAD_FORGE", True)

SPRITE_PROMPT_PREFIX = "pixel art, game sprite, single object, centered, full body, flat colors, plain white background, "
SPRITE_NEGATIVE = ("text, watermark, signature, multiple objects, cropped, blurry, photo, realistic, 3d render, "
                   "scenery, landscape, border, frame, shadow on ground")
BG_PROMPT_SUFFIX = ", pixel art, 2d game background, wide scenery, no characters, no text"
BG_NEGATIVE = "text, watermark, characters, people, ui, frame, blurry, 3d render"

# ---- Sprite post-processing ------------------------------------------------
REMBG_MODEL = _env("HARNESS_REMBG_MODEL", "u2net")
PIXEL_GRID = _env_int("HARNESS_PIXEL_GRID", 32)   # logical pixels per sprite side; 0 disables pixelation
PALETTE_COLORS = _env_int("HARNESS_PALETTE", 24)  # 0 disables colour quantisation
BG_GRID = (200, 150)                               # background logical resolution

# ---- Music (MusicGen via transformers) -------------------------------------
MUSIC_BACKEND = _env("HARNESS_MUSIC", "musicgen")   # musicgen | none
MUSIC_MODEL = _env("HARNESS_MUSIC_MODEL", _P["music_model"])
MUSIC_SECONDS = _env_int("HARNESS_MUSIC_SECONDS", 15)

# ---- Game / loop -----------------------------------------------------------
CANVAS_W, CANVAS_H = 800, 600
MAX_FIX_ROUNDS = _env_int("HARNESS_MAX_FIXES", 3)
RAG_TOP_K = _env_int("HARNESS_RAG_K", 3)
SOAK_SECONDS = _env_int("HARNESS_SOAK", 10)          # how long the test plays the game
