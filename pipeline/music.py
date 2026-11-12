"""BGM stage: MusicGen (open weights, via Hugging Face transformers) makes a short loop.

If MusicGen cannot run (no GPU, missing packages, no internet for the first download) this
returns None and the runtime falls back to its built-in procedural chiptune - the pipeline
never fails because of music.
"""
import gc
import wave
from pathlib import Path

import numpy as np

from . import config
from .util import say

MUSICGEN_TOKENS_PER_SECOND = 50


def loopify(wav, sr, fade_seconds=1.0):
    """Crossfade the tail into the head so the clip loops without a click."""
    n = int(sr * fade_seconds)
    if len(wav) < n * 3:
        return wav
    body = wav[:-n].copy()
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)
    body[:n] = body[:n] * ramp + wav[-n:] * (1.0 - ramp)
    return body


def write_wav(path, wav, sr):
    wav = np.asarray(wav, dtype=np.float32)
    peak = float(np.max(np.abs(wav))) or 1.0
    pcm = (wav / peak * 0.9 * 32767).astype(np.int16)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(int(sr))
        f.writeframes(pcm.tobytes())


def available():
    try:
        import torch  # noqa: F401
        import transformers  # noqa: F401
        return True, ("cuda" if torch.cuda.is_available() else "cpu")
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:100]


def generate(prompt, out_wav, seconds=None):
    """Returns the WAV path, or None if music generation is disabled/unavailable."""
    if config.MUSIC_BACKEND == "none":
        return None
    seconds = seconds or config.MUSIC_SECONDS
    ok, device = available()
    if not ok:
        say(f"  [music] MusicGen unavailable ({device}); runtime chiptune will be used")
        return None
    try:
        import torch
        from transformers import AutoProcessor, MusicgenForConditionalGeneration
        if device == "cpu":
            say("  [music] no CUDA GPU visible to PyTorch - this will be slow (minutes)")
        say(f"  [music] loading {config.MUSIC_MODEL} (first run downloads ~2.4 GB)")
        processor = AutoProcessor.from_pretrained(config.MUSIC_MODEL)
        model = MusicgenForConditionalGeneration.from_pretrained(config.MUSIC_MODEL).to(device)
        inputs = processor(text=[prompt], padding=True, return_tensors="pt").to(device)
        say(f"  [music] generating {seconds}s: {prompt}")
        with torch.no_grad():
            audio = model.generate(**inputs, do_sample=True, guidance_scale=3.0,
                                   max_new_tokens=int(seconds * MUSICGEN_TOKENS_PER_SECOND))
        sr = model.config.audio_encoder.sampling_rate
        wav = audio[0, 0].detach().cpu().float().numpy()
        write_wav(out_wav, loopify(wav, sr), sr)
        del model, processor, inputs, audio
        gc.collect()
        if device == "cuda":
            torch.cuda.empty_cache()
        return Path(out_wav)
    except Exception as e:  # noqa: BLE001
        say(f"  [music] MusicGen failed ({str(e)[:120]}); runtime chiptune will be used")
        return None
