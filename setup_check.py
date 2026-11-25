#!/usr/bin/env python3
"""Environment helper.

    python setup_check.py                       # pre-flight: what is installed / running?
    python setup_check.py --prefetch            # download every model the harness needs (setup.bat runs this)
    python setup_check.py --enable-forge-api    # only for the optional Forge backend (HARNESS_IMAGE_BACKEND=forge)

Which models are downloaded depends on the hardware profile (pipeline/config.py): a 16 GB GPU gets the
larger ones (Qwen2.5-Coder 14B, SDXL + pixel-art LoRA, MusicGen-medium), an 8 GB GPU the smaller ones.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

from pipeline import config, llm, services
from pipeline.util import say, setup_console


def enable_forge_api(forge_dir):
    root = Path(forge_dir) if forge_dir else None
    if not root or not root.exists():
        say("Pass the Forge folder:  python setup_check.py --enable-forge-api --forge-dir \"C:\\path\\to\\Forge\"  (or set FORGE_DIR)")
        return 1
    matches = sorted(root.rglob("webui-user.bat"), key=lambda p: len(p.parts))
    if not matches:
        say(f"No webui-user.bat found under {root}")
        return 1
    bat = matches[0]
    raw = bat.read_bytes().decode("latin-1")          # latin-1 round-trips every byte, so line endings / encoding survive
    m = re.search(r"^(\s*set\s+COMMANDLINE_ARGS=)(.*?)(\r?)$", raw, re.M | re.I)
    if m and "--api" in m.group(2):
        say(f"--api is already enabled in {bat}")
        return 0
    bat.with_suffix(".bat.bak").write_bytes(raw.encode("latin-1"))
    if m:
        new = m.group(1) + (m.group(2).strip() + " --api").strip() + m.group(3)
        raw = raw[:m.start()] + new + raw[m.end():]
    else:
        raw = raw.rstrip("\r\n") + "\r\nset COMMANDLINE_ARGS=--api\r\n"
    bat.write_bytes(raw.encode("latin-1"))
    say(f"Added --api to {bat}  (backup: {bat.with_suffix('.bat.bak').name}). Restart Forge with run.bat.")
    return 0


def _ollama_pull(model):
    """Pull with a progress line (a 9 GB model can take a while and should not look frozen)."""
    r = requests.post(config.OLLAMA_URL + "/api/pull", json={"model": model, "stream": True}, stream=True, timeout=7200)
    if r.status_code != 200:
        return False, r.text[:160]
    last, shown = "", 0.0
    for line in r.iter_lines():
        if not line:
            continue
        msg = json.loads(line)
        if msg.get("error"):
            return False, msg["error"][:160]
        status, total, done = msg.get("status", ""), msg.get("total"), msg.get("completed")
        if total and done and time.time() - shown > 2:
            say(f"    {model}: {status} {done / 2**30:.1f}/{total / 2**30:.1f} GB ({100 * done / total:.0f}%)")
            shown = time.time()
        elif status != last and not total:
            say(f"    {model}: {status}")
        last = status
    return True, "ok"


def _step(title, fn):
    say(title)
    try:
        fn()
        say("  ok")
        return True
    except Exception as e:  # noqa: BLE001
        say(f"  FAILED: {str(e)[:200]}")
        return False


def prefetch():
    from pipeline import services
    say("Hardware profile: " + services.profile_line())
    ok_all = True
    say("Ollama models:")
    if llm.list_models() is None:
        say(f"  Ollama is not reachable at {config.OLLAMA_URL} - start it, then run this again")
        ok_all = False
    else:
        for model in dict.fromkeys((config.CODE_MODEL, config.PLAN_MODEL, config.EMBED_MODEL)):
            if llm.has_model(model):
                say(f"  {model}: already installed")
                continue
            say(f"  pulling {model}")
            ok, msg = _ollama_pull(model)
            say(f"  {model}: {msg}")
            ok_all &= ok

    if config.IMAGE_BACKEND != "forge":
        def image():
            import torch
            from diffusers import DiffusionPipeline
            from huggingface_hub import hf_hub_download, snapshot_download
            try:
                DiffusionPipeline.download(config.IMAGE_MODEL, variant="fp16", use_safetensors=True, torch_dtype=torch.float16)
            except (OSError, ValueError):
                DiffusionPipeline.download(config.IMAGE_MODEL, use_safetensors=True)
            if config.IMAGE_VAE:
                snapshot_download(config.IMAGE_VAE, allow_patterns=["config.json", "diffusion_pytorch_model.safetensors"])
            if config.IMAGE_LORA:
                hf_hub_download(config.IMAGE_LORA, config.IMAGE_LORA_FILE)
        ok_all &= _step(f"Image model {config.IMAGE_MODEL}" + (f" + {config.IMAGE_LORA}" if config.IMAGE_LORA else "")
                        + " (several GB)...", image)

    def rembg_model():
        from rembg import new_session
        new_session(config.REMBG_MODEL)
    ok_all &= _step("Background-removal model (rembg / U2-Net, ~170 MB)...", rembg_model)

    if config.MUSIC_BACKEND != "none":
        def musicgen():
            from transformers import AutoProcessor, MusicgenForConditionalGeneration
            AutoProcessor.from_pretrained(config.MUSIC_MODEL)
            MusicgenForConditionalGeneration.from_pretrained(config.MUSIC_MODEL)
        ok_all &= _step(f"MusicGen ({config.MUSIC_MODEL})...", musicgen)
    say("\nAll models downloaded." if ok_all else "\nSome downloads failed - see above, then run this again.")
    return 0 if ok_all else 1


def main():
    setup_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--enable-forge-api", action="store_true")
    ap.add_argument("--forge-dir", default=config.FORGE_DIR)
    ap.add_argument("--prefetch", action="store_true")
    args = ap.parse_args()
    if args.enable_forge_api:
        return enable_forge_api(args.forge_dir)
    if args.prefetch:
        return prefetch()
    ok = services.print_checks(services.run_checks())
    say("\nAll required checks passed." if ok else "\nSome required checks failed - see the hints above.")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
