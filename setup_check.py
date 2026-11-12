#!/usr/bin/env python3
"""Environment helper.

    python setup_check.py                       # pre-flight: what is installed / running?
    python setup_check.py --enable-forge-api    # add --api to Forge's webui-user.bat (backs the file up first)
    python setup_check.py --prefetch            # download the models the harness needs (run once, with internet)
"""
import argparse
import re
import sys
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


def prefetch():
    say("Pulling Ollama models...")
    for model in (config.CODE_MODEL, config.EMBED_MODEL):
        if llm.has_model(model):
            say(f"  {model}: already installed")
            continue
        say(f"  pulling {model} (this can take a while)")
        r = requests.post(config.OLLAMA_URL + "/api/pull", json={"model": model, "stream": False}, timeout=3600)
        say(f"  {model}: {'ok' if r.status_code == 200 else 'failed ' + r.text[:120]}")
    say("Downloading the background-removal model (rembg / U2-Net, ~170 MB)...")
    try:
        from rembg import new_session
        new_session(config.REMBG_MODEL)
        say("  ok")
    except Exception as e:  # noqa: BLE001
        say(f"  skipped: {str(e)[:120]}")
    say(f"Downloading MusicGen ({config.MUSIC_MODEL}, ~2.4 GB)...")
    try:
        from transformers import AutoProcessor, MusicgenForConditionalGeneration
        AutoProcessor.from_pretrained(config.MUSIC_MODEL)
        MusicgenForConditionalGeneration.from_pretrained(config.MUSIC_MODEL)
        say("  ok")
    except Exception as e:  # noqa: BLE001
        say(f"  skipped: {str(e)[:120]}")
    return 0


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
