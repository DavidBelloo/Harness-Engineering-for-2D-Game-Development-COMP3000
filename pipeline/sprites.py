"""Art stage: Stable Diffusion -> background removal -> sprite clean-up.

Two interchangeable image backends (config.IMAGE_BACKEND):
  diffusers  (default) Stable Diffusion runs inside this Python process via Hugging Face `diffusers`.
             Nothing extra to install or start; weights download from Hugging Face on first use.
             High profile: SDXL + fp16-fixed VAE + pixel-art LoRA. Low profile: SD 1.5.
  forge      an external Stable Diffusion Forge started with --api (the original setup).

Raw diffusion output is never usable as a sprite (white box, photoreal detail, wrong size),
so every image goes through: cut-out -> crop -> fit -> pixelate -> palette reduction.
"""
import base64
import gc
import io
import random
from collections import deque
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageEnhance

from . import config
from .util import say


class ImageGenError(RuntimeError):
    pass


ForgeError = ImageGenError          # old name, kept for compatibility

FORGE_HELP = ("Cannot reach the Forge API at {url}. Start Forge with the --api flag "
              "(set COMMANDLINE_ARGS=--api in webui\\webui-user.bat, or run `python setup_check.py --enable-forge-api`), "
              "then run.bat, and wait for 'Running on local URL'. Or use the built-in backend: HARNESS_IMAGE_BACKEND=diffusers")


# ---- backend: Forge (external app, HTTP API) ------------------------------------
def forge_up():
    try:
        return requests.get(config.FORGE_URL + "/sdapi/v1/options", timeout=5).status_code == 200
    except Exception:  # noqa: BLE001
        return False


def _forge_txt2img(prompt, negative, width, height, seed):
    if config.FORGE_LORA:
        prompt = f"{prompt}, <lora:{config.FORGE_LORA}>"
    payload = {"prompt": prompt, "negative_prompt": negative, "steps": config.IMAGE_STEPS, "cfg_scale": config.IMAGE_CFG,
               "width": width, "height": height, "sampler_name": config.FORGE_SAMPLER, "seed": seed,
               "batch_size": 1, "n_iter": 1}
    if config.FORGE_CHECKPOINT:
        payload["override_settings"] = {"sd_model_checkpoint": config.FORGE_CHECKPOINT}
    try:
        r = requests.post(config.FORGE_URL + "/sdapi/v1/txt2img", json=payload, timeout=config.FORGE_TIMEOUT)
    except requests.ConnectionError as e:
        raise ImageGenError(FORGE_HELP.format(url=config.FORGE_URL)) from e
    if r.status_code != 200:
        raise ImageGenError(f"Forge returned HTTP {r.status_code}: {r.text[:300]}")
    b64 = r.json()["images"][0]
    if "," in b64[:64]:
        b64 = b64.split(",", 1)[1]
    return Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGBA")


def _forge_unload():
    if not config.UNLOAD_FORGE:
        return
    try:
        requests.post(config.FORGE_URL + "/sdapi/v1/unload-checkpoint", timeout=30)
    except Exception:  # noqa: BLE001
        pass


# ---- backend: diffusers (in-process) ----------------------------------------------
_pipe = {}


def _torch_device():
    import torch
    if torch.cuda.is_available():
        return "cuda", torch.float16
    return "cpu", torch.float32


def _load_pipeline():
    """Load (once) the text-to-image pipeline for the active profile, onto the GPU in fp16."""
    if "p" in _pipe:
        return _pipe["p"]
    import torch
    from diffusers import AutoencoderKL, AutoPipelineForText2Image, EulerAncestralDiscreteScheduler
    device, dtype = _torch_device()
    if device == "cpu":
        say("  [art] no CUDA GPU visible to PyTorch - images will take minutes each (or use --skip-art)")
    say(f"  [art] loading {config.IMAGE_MODEL} on {device} (first run downloads the weights)")
    kwargs = {"torch_dtype": dtype, "use_safetensors": True}
    if config.IMAGE_VAE:
        kwargs["vae"] = AutoencoderKL.from_pretrained(config.IMAGE_VAE, torch_dtype=dtype)
    if "stable-diffusion-v1" in config.IMAGE_MODEL or "stable-diffusion-1" in config.IMAGE_MODEL:
        kwargs.update(safety_checker=None, requires_safety_checker=False)   # false positives give black sprites
    try:
        pipe = AutoPipelineForText2Image.from_pretrained(config.IMAGE_MODEL, variant="fp16" if dtype == torch.float16 else None, **kwargs)
    except (OSError, ValueError):            # repo without an fp16 variant: load the full-precision files
        pipe = AutoPipelineForText2Image.from_pretrained(config.IMAGE_MODEL, **kwargs)
    pipe.scheduler = EulerAncestralDiscreteScheduler.from_config(pipe.scheduler.config)
    if config.IMAGE_LORA:
        try:
            pipe.load_lora_weights(config.IMAGE_LORA, weight_name=config.IMAGE_LORA_FILE or None, adapter_name="style")
            pipe.set_adapters(["style"], adapter_weights=[config.IMAGE_LORA_SCALE])
            say(f"  [art] style LoRA: {config.IMAGE_LORA} x{config.IMAGE_LORA_SCALE}")
        except Exception as e:  # noqa: BLE001
            say(f"  [art] LoRA {config.IMAGE_LORA} not loaded ({str(e)[:90]}); continuing without it")
    pipe = pipe.to(device)
    pipe.set_progress_bar_config(disable=True)
    if device == "cuda":
        pipe.enable_vae_slicing()
    _pipe["p"] = pipe
    return pipe


def _diffusers_txt2img(prompt, negative, width, height, seed):
    import torch
    pipe = _load_pipeline()
    device, _ = _torch_device()
    gen = torch.Generator(device=device).manual_seed(int(seed))
    with torch.inference_mode():
        out = pipe(prompt=prompt, negative_prompt=negative, width=width, height=height,
                   num_inference_steps=config.IMAGE_STEPS, guidance_scale=config.IMAGE_CFG, generator=gen)
    return out.images[0].convert("RGBA")


def _diffusers_unload():
    if "p" not in _pipe:
        return
    del _pipe["p"]
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001
        pass


def _diffusers_ready():
    try:
        import diffusers  # noqa: F401
        import torch
    except Exception as e:  # noqa: BLE001
        return False, f"diffusers/torch not installed ({str(e)[:80]}) - run setup.bat"
    if not torch.cuda.is_available():
        return True, "no CUDA GPU visible to PyTorch: images will be very slow (use --skip-art)"
    return True, f"{config.IMAGE_MODEL} on {torch.cuda.get_device_name(0)}"


# ---- backend-neutral API used by the pipeline and the MCP server ----------------
def ready():
    """(ok, detail): can the configured image backend generate right now?"""
    if config.IMAGE_BACKEND == "forge":
        up = forge_up()
        return up, (config.FORGE_URL if up else FORGE_HELP.format(url=config.FORGE_URL))
    return _diffusers_ready()


def txt2img(prompt, negative, width, height, seed=-1):
    seed = random.randint(1, 2**31 - 1) if seed is None or seed < 0 else seed
    if config.IMAGE_BACKEND == "forge":
        return _forge_txt2img(prompt, negative, width, height, seed)
    return _diffusers_txt2img(prompt, negative, width, height, seed)


def unload():
    """Release the image model's VRAM before the LLM / MusicGen need the GPU."""
    if config.IMAGE_BACKEND == "forge":
        _forge_unload()
    else:
        _diffusers_unload()


unload_forge = unload               # old name, kept for compatibility


# ---- background removal -----------------------------------------------------
_session = {}


def _rembg(img):
    from rembg import new_session, remove
    if "s" not in _session:
        _session["s"] = new_session(config.REMBG_MODEL)
    return remove(img, session=_session["s"]).convert("RGBA")


def _flood_cutout(img, tol=70):
    """Fallback cut-out: flood-fill from the border through pixels close to the border colour."""
    arr = np.array(img.convert("RGBA")).astype(np.int16)
    h, w = arr.shape[:2]
    border = np.concatenate([arr[0, :, :3], arr[-1, :, :3], arr[:, 0, :3], arr[:, -1, :3]])
    bg = np.median(border, axis=0)
    near = (np.abs(arr[:, :, :3] - bg).sum(axis=2) <= tol)
    seen = np.zeros((h, w), dtype=bool)
    dq = deque()
    for x in range(w):
        for y in (0, h - 1):
            if near[y, x] and not seen[y, x]:
                seen[y, x] = True; dq.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if near[y, x] and not seen[y, x]:
                seen[y, x] = True; dq.append((y, x))
    while dq:
        y, x = dq.popleft()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < h and 0 <= nx < w and near[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True; dq.append((ny, nx))
    arr[seen, 3] = 0
    return Image.fromarray(arr.astype(np.uint8), "RGBA")


def remove_background(img):
    """Returns (RGBA image, method). Tries rembg (U2-Net), falls back to flood fill."""
    method = "rembg"
    try:
        out = _rembg(img)
    except Exception as e:  # noqa: BLE001
        say(f"  [art] rembg unavailable ({str(e)[:70]}); using flood-fill cut-out")
        out, method = _flood_cutout(img), "floodfill"
    alpha = np.array(out.getchannel("A"))
    frac = float((alpha > 16).mean())
    if frac < 0.02 or frac > 0.97:                       # cut-out failed: removed everything / nothing
        if method == "rembg":
            alt = _flood_cutout(img)
            f2 = float((np.array(alt.getchannel("A")) > 16).mean())
            if 0.02 <= f2 <= 0.97:
                return alt, "floodfill"
        return img, "none"
    return out, method


# ---- sprite finishing ---------------------------------------------------------
def _quantize(rgb, colors):
    return rgb.quantize(colors=colors, method=Image.Quantize.MEDIANCUT).convert("RGB") if colors else rgb


def finish_sprite(img, w, h):
    """Crop to the object, fit into w x h, pixelate, reduce palette, hard alpha edges."""
    bbox = img.getchannel("A").point(lambda a: 255 if a > 16 else 0).getbbox()
    if bbox:
        img = img.crop(bbox)
    inner_w, inner_h = max(1, w - 4), max(1, h - 4)
    scale = min(inner_w / img.width, inner_h / img.height)
    img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    canvas.paste(img, ((w - img.width) // 2, (h - img.height) // 2), img)
    if config.PIXEL_GRID > 0:
        g = config.PIXEL_GRID
        gw, gh = max(8, round(g * w / max(w, h))), max(8, round(g * h / max(w, h)))
        small = canvas.resize((gw, gh), Image.Resampling.BOX)
        alpha = small.getchannel("A").point(lambda a: 255 if a >= 128 else 0)
        rgb = _quantize(small.convert("RGB"), config.PALETTE_COLORS)
        small = Image.merge("RGBA", (*rgb.split(), alpha))
        canvas = small.resize((w, h), Image.Resampling.NEAREST)
    return canvas


def finish_background(img):
    gw, gh = config.BG_GRID
    small = img.convert("RGB").resize((gw, gh), Image.Resampling.BOX)
    small = _quantize(small, 32)
    out = small.resize((config.CANVAS_W, config.CANVAS_H), Image.Resampling.NEAREST)
    return ImageEnhance.Brightness(out).enhance(0.75).convert("RGBA")   # darker so sprites stand out


# ---- placeholders (used with --skip-art) --------------
_PALETTE = [(240, 120, 90), (90, 170, 240), (120, 210, 120), (240, 210, 90), (190, 130, 230), (240, 150, 190)]


def placeholder_sprite(name, w, h, index=0):
    from PIL import ImageDraw
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((2, 2, w - 3, h - 3), radius=max(4, min(w, h) // 5), fill=_PALETTE[index % len(_PALETTE)] + (255,),
                        outline=(255, 255, 255, 255), width=2)
    d.text((w // 2 - 3, h // 2 - 5), name[:1].upper(), fill=(0, 0, 0, 255))
    return img


# ---- orchestration --------------------------------------------------------------
def make_sprite(desc, w, h, seed=None):
    seed = random.randint(1, 2**31 - 1) if seed is None else seed
    raw = txt2img(config.SPRITE_PROMPT_PREFIX + desc, config.SPRITE_NEGATIVE,
                  config.SPRITE_GEN_SIZE, config.SPRITE_GEN_SIZE, seed)
    cut, method = remove_background(raw)
    return finish_sprite(cut, w, h), raw, {"seed": seed, "cutout": method}


def make_background(desc, seed=None):
    seed = random.randint(1, 2**31 - 1) if seed is None else seed
    raw = txt2img(desc + config.BG_PROMPT_SUFFIX, config.BG_NEGATIVE, config.BG_GEN_SIZE[0], config.BG_GEN_SIZE[1], seed)
    return finish_background(raw), raw, {"seed": seed}


def generate_assets(plan, assets_dir):
    """Generate every sprite (+ optional background) in the plan. Returns (paths, info)."""
    ok, detail = ready()
    if not ok:
        raise ImageGenError(detail)
    assets_dir = Path(assets_dir)
    (assets_dir / "raw").mkdir(parents=True, exist_ok=True)
    paths, info = {}, {"sprites": {}, "background": None}
    for s in plan["sprites"]:
        say(f"  [art] sprite '{s['name']}': {s['description']}")
        img, raw, meta = make_sprite(s["description"], s["width"], s["height"])
        raw.save(assets_dir / "raw" / f"{s['name']}_raw.png")
        out = assets_dir / f"{s['name']}.png"
        img.save(out)
        paths[s["name"]] = out
        info["sprites"][s["name"]] = meta
    bg_path = None
    if plan.get("background"):
        say(f"  [art] background: {plan['background']}")
        img, raw, meta = make_background(plan["background"])
        raw.save(assets_dir / "raw" / "background_raw.png")
        bg_path = assets_dir / "background.png"
        img.save(bg_path)
        info["background"] = meta
    return paths, bg_path, info
