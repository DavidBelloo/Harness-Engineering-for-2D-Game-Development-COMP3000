# Design Document - Harness Engineering for 2D Game Development

## 1. Goal and constraints
Turn a one-sentence prompt into a playable 2D prototype with novel generated assets. No game engine, no frontier model in the harness, everything local on one consumer GPU (8 GB dev PC; 16 GB RTX 5080 test machine). The human writes no game code, and setting the harness up on a fresh machine should take one step.

## 2. Components (code / art / animation / sfx / bgm / orchestration)
Models are chosen from the GPU's memory (`pipeline/config.py`), so one repo serves both machines.

| Role | 16 GB GPU ("high") | 8 GB GPU ("low") | Why | Alternatives considered |
|---|---|---|---|---|
| Code | Qwen2.5-Coder 14B (Ollama) | Qwen2.5-Coder 7B | strongest coder that fits; the 7B's failures were simple bugs a larger model makes less often | Qwen3-Coder 30B (MoE) - to benchmark; too large for 8 GB |
| Art | SDXL + fp16-fixed VAE + Pixel Art XL LoRA, in-process (diffusers) -> rembg -> pixelate -> palette | SD 1.5 (diffusers), same clean-up | SDXL follows prompts better (SD 1.5 drew the "ghost" as a person); the LoRA gives real pixel-art style | Forge (external app, kept as an optional backend) |
| Animation | `Anim`/`Particles` helpers (bob, pulse, shake, flash) in the runtime | same | small models cannot invent animation from scratch; give them a vocabulary | sprite-sheet generation (unreliable) |
| SFX | Web Audio presets selected by the planner | same | zero VRAM, instant | AudioGen (extra VRAM/time) |
| BGM | MusicGen-medium, 15 s crossfaded loop | MusicGen-small | better quality once VRAM allows | chiptune fallback if unavailable |
| Orchestration | fixed Python pipeline + MCP server | same | reliable with small models | free-form agent loop (see failures) |

## 3. Architecture
```
idea -> planner (JSON plan: title, sprites, sfx, controls)
     -> RAG (hybrid embeddings + BM25 over 15 pattern docs, mechanic quota)
     -> coder (skill prompt + patterns + plan) -> game.js
     -> unload LLM -> Stable Diffusion sprites + background -> unload -> MusicGen
     -> assemble: runtime-helpers.js + assets (base64) + game.js -> ONE html
     -> headless-browser test (scripted + random input) -> report -> LLM fix loop (max 3)
```
The "engine" is a ~300-line helper runtime (`skills/runtime-helpers.js`: input, sprite drawing, audio, particles, game loop). It is the harness's shared vocabulary, not a game engine: it has no physics, scene graph or editor, and the model writes all game logic.

**VRAM hand-off:** LLM, Stable Diffusion and MusicGen cannot co-reside in one GPU (8 GB, and still not with the larger models on 16 GB), so each stage ends by unloading its model (Ollama `keep_alive:0`, releasing the diffusers pipeline and emptying the CUDA cache).

**Setup:** `setup.bat` -> `setup.ps1` installs everything per-user in one step: uv (which provides Python 3.12), the pinned packages from `pyproject.toml` with PyTorch for CUDA 12.8, a test browser, Ollama, and every model for the detected profile, then runs the pre-flight check. `run.bat` makes a game.

**Verification:** the checker plays the game in headless Chromium/Edge, reporting JS errors with the offending line of the model's code, blank or frozen canvas, sprites never drawn, and whether the game can end. That report is the fix-loop prompt.

## 4. Failed attempts and lessons learned
1. **Forge cu124 build crashed on Windows 11** (missing `libomp140.x86_64.dll`, fbgemm load failure). Fixed by using the `cu121_torch231` build. Lesson: pin the whole GPU stack; test it before building on top.
2. **`pip uninstall torch` hit system Python, not Forge's bundled Python.** Lesson: multiple Pythons - always check which interpreter is running.
3. **First game: white box around the sprite.** Raw diffusion output has a background. Fixed with rembg cut-out + flood-fill fallback. Lesson: generated assets need post-processing before use.
4. **Model-written games that "run" but are broken** (frozen or blank canvas, wrong sprite names). A syntax/no-error check is not enough; the checker now looks at pixels and drawn sprites. Lesson: test behaviour, not just errors.
5. **RAG retrieval crowded by generic docs** (lives/restart matched every idea) and missed "shooting" vs "shoot". Fixed with stemming, BM25 + curated keywords, and a quota reserving slots for genre docs with a relevance floor. Lesson: tune retrieval on real queries.
6. **Heavy dependencies avoided:** chromadb needs a C++ compiler on Windows; for 15 docs a numpy store is enough. mcp 2.x broke the API, so it is pinned `<2`.
7. **Free-form agent loop rejected** for the main path: a 7B model loses the thread; a fixed pipeline with LLM calls only where needed is far more reliable. MCP server kept for agentic use.

### Version 2: the lab machine (RTX 5080) and one-step setup
8. **Setting the harness up on another computer was too hard.** Even with the GitHub repo, a fresh machine needed eight separate installs in the right order (Python of the right version, a CUDA build of PyTorch installed before everything else, Forge downloaded and extracted, a checkpoint copied in, Forge's `--api` flag, Ollama, models, a browser). Fixed by removing steps rather than documenting them: images are now generated inside the harness's own Python process (diffusers), so Forge, the checkpoint copy and the API flag are gone; uv downloads the right Python itself; one script does the rest. Lesson: the cheapest setup step is the one you delete.
9. **The pinned GPU stack would not run on an RTX 5080.** The 50-series (Blackwell) needs PyTorch 2.7+ built for CUDA 12.8; the torch 2.3.1/CUDA 12.1 stack (and the Forge build on top of it) fails with "no kernel image is available". The pre-flight check now runs a real CUDA kernel instead of only asking whether CUDA exists, because a mismatched build still reports CUDA as available. Lesson: "pin the stack" (lesson 1) must be re-checked whenever the hardware changes.
10. **One configuration for two machines.** Model sizes are chosen from the GPU's memory, so the same repo runs the 7B/SD 1.5 set on the 8 GB dev PC and the 14B/SDXL set on the 16 GB lab machine, with environment-variable overrides for experiments.

## 5. Evaluation
`run.bat --batch prompts\benchmark.txt` runs 6 varied ideas and writes a table of pass/fail, time and fix rounds.

| Run | Machine / profile | Passed | Notes |
|---|---|---|---|
| 12 Nov | RTX 4060 8 GB, low (Qwen 7B, SD 1.5) | 3/6 | failures: repeated simple bugs; led to the rewrite-on-repeated-error fix loop |
| `[date]` | RTX 5080 16 GB, high (Qwen 14B, SDXL) | `[ ]/6` | `[fill in]` |

## 6. Limitations / next
One level, single screen; no animation sheets; code quality still varies by genre; first run downloads 15-25 GB of models.
