"""Thin client for a local Ollama server (open-weights models only)."""
import json
import time
from dataclasses import dataclass

import requests

from . import config
from .util import say, say_inline


class OllamaError(RuntimeError):
    pass


@dataclass
class LLMResult:
    text: str
    tokens: int
    seconds: float


def _post(path, payload, stream=False, timeout=900):
    try:
        return requests.post(config.OLLAMA_URL + path, json=payload, stream=stream, timeout=timeout)
    except requests.ConnectionError as e:
        raise OllamaError(f"Cannot reach Ollama at {config.OLLAMA_URL}. Start the Ollama app "
                          "(system tray icon) or run `ollama serve`.") from e


def list_models():
    try:
        r = requests.get(config.OLLAMA_URL + "/api/tags", timeout=5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:  # noqa: BLE001
        return None


def has_model(name, models=None):
    models = models if models is not None else (list_models() or [])
    return any(m == name or m == name + ":latest" or m.split(":")[0] == name for m in models)


def chat(messages, model=None, json_mode=False, temperature=0.2, num_predict=4096, label="llm", show_progress=True, seed=None):
    model = model or config.CODE_MODEL
    payload = {"model": model, "messages": messages, "stream": True, "keep_alive": "10m",
               "options": {"temperature": temperature, "num_ctx": config.NUM_CTX, "num_predict": num_predict}}
    if seed is not None:
        payload["options"]["seed"] = int(seed)
    if json_mode:
        payload["format"] = "json"
    t0 = time.time()
    r = _post("/api/chat", payload, stream=True)
    if r.status_code == 404:
        raise OllamaError(f"Model '{model}' is not installed. Run: ollama pull {model}")
    if r.status_code != 200:
        raise OllamaError(f"Ollama returned HTTP {r.status_code}: {r.text[:300]}")
    parts, n, final = [], 0, {}
    for line in r.iter_lines():
        if not line:
            continue
        obj = json.loads(line)
        if obj.get("error"):
            raise OllamaError(obj["error"])
        piece = (obj.get("message") or {}).get("content", "")
        if piece:
            parts.append(piece)
            n += 1
            if show_progress and n % 25 == 0:
                say_inline(f"\r  [{label}] {n} tokens...")
        if obj.get("done"):
            final = obj
    secs = time.time() - t0
    tokens = final.get("eval_count") or n
    if show_progress:
        say(f"\r  [{label}] {tokens} tokens in {secs:.1f}s ({tokens / max(secs, 0.01):.0f} tok/s)      ")
    return LLMResult("".join(parts), tokens, secs)


def unload(model=None):
    """Free the model's VRAM so Stable Diffusion / MusicGen can use the GPU."""
    try:
        requests.post(config.OLLAMA_URL + "/api/generate", json={"model": model or config.CODE_MODEL, "keep_alive": 0}, timeout=30)
    except Exception:  # noqa: BLE001
        pass


def embed(texts, model=None):
    model = model or config.EMBED_MODEL
    r = _post("/api/embed", {"model": model, "input": list(texts)}, timeout=120)
    if r.status_code == 200:
        return r.json()["embeddings"]
    if r.status_code == 404 and "not found" in r.text.lower():
        raise OllamaError(f"Embedding model '{model}' is not installed. Run: ollama pull {model}")
    # very old Ollama: one call per text
    out = []
    for t in texts:
        rr = _post("/api/embeddings", {"model": model, "prompt": t}, timeout=120)
        if rr.status_code != 200:
            raise OllamaError(f"Embedding failed: HTTP {rr.status_code} {rr.text[:200]}")
        out.append(rr.json()["embedding"])
    return out
