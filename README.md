# Harness Engineering for 2D Game Development (COMP3000)

An open-source orchestration harness that lets non-technical game developers generate 2D game prototypes, including original assets, from text prompts.

```
run.bat "a ghost dodging falling pumpkins, you lose after three hits"
```
Result: one self-contained `game.html` (art, music and code inside it) that opens in any browser. No game engine, and no frontier/cloud model inside the harness: every model runs locally.

## Setup on a fresh Windows PC (one step)

Needs: Windows 10/11, an NVIDIA GPU with an up-to-date driver, internet, and roughly 40 GB of free disk space.

1. Get the project: **Code > Download ZIP** on GitHub and extract it, or `git clone` it.
2. Double-click **`setup.bat`**.

That's it. `setup.bat` installs everything per-user (no admin rights needed) and is safe to run again; finished steps are skipped:

| Step | What it does |
|---|---|
| 1 | Checks the NVIDIA GPU and driver (RTX 50-series needs driver 570 or newer) |
| 2 | Installs **uv**, which downloads Python 3.12 itself, so no Python install is needed |
| 3 | Installs the Python packages, including PyTorch 2.7 for CUDA 12.8 (works on RTX 20/30/40/50) |
| 4 | Installs a browser for the automated game test (Edge is used if this fails) |
| 5 | Installs and starts **Ollama** (runs the language models) |
| 6 | Downloads every AI model for this machine (15 to 25 GB the first time) |
| 7 | Runs the pre-flight check |

A log is written to `setup.log`.

## Make a game

```
run.bat "a cat flying a rocket and shooting asteroids"
run.bat                                     (asks you for the idea)
run.bat --batch prompts\benchmark.txt       (benchmark: writes output\benchmark_*.md)
run.bat "idea" --skip-art --no-music        (fast test without the image/music models)
```
`run.bat` starts Ollama if needed. The game opens in your browser when it's done, and is saved in `output\<run>\game.html` and `output\latest_game.html`. `check.bat` re-runs the pre-flight check.

## Models (picked automatically from the GPU's memory)

| Part | 16 GB GPU (e.g. RTX 5080) - "high" | 8-12 GB GPU (e.g. RTX 4060) - "low" |
|---|---|---|
| Code + planning | Qwen2.5-Coder 14B (Ollama) | Qwen2.5-Coder 7B |
| Retrieval (RAG) | nomic-embed-text + BM25 over `docs/` | same |
| Art | SDXL + fp16-fixed VAE + Pixel Art XL LoRA (diffusers) | Stable Diffusion 1.5 (diffusers) |
| Art clean-up | rembg cut-out, pixelation, palette reduction | same |
| Music | MusicGen-medium | MusicGen-small |
| Sound effects / animation | Web Audio presets / runtime JS helpers | same |

Override anything with environment variables, e.g. `set HARNESS_PROFILE=low` or `set HARNESS_CODE_MODEL=qwen3-coder:30b` (see `pipeline/config.py`).

## How it works
```
idea -> plan (LLM, JSON) -> retrieve game patterns (RAG) -> write game code (LLM)
     -> sprites + background (Stable Diffusion) -> music (MusicGen)
     -> assemble one HTML -> play it in a headless browser -> report errors -> LLM fixes (max 3 rounds)
```
Each model is unloaded before the next stage so they share one GPU. Details and lessons learned: `DESIGN.md`.

## MCP mode (agents)
`mcp_server.py` exposes the same steps as MCP tools: `list_runtime_api`, `search_game_docs`, `generate_sprite`, `generate_background`, `generate_music`, `assemble_game`, `test_game`. MCP client config:
```json
{"mcpServers": {"game-harness": {"command": "uv", "args": ["run", "--directory", "C:/path/to/this/folder", "python", "mcp_server.py"]}}}
```

## Troubleshooting
| Problem | Fix |
|---|---|
| `PyTorch ... cannot run on NVIDIA GeForce RTX 50xx` | Needs torch 2.7+ for CUDA 12.8. Run `setup.bat` again; update the NVIDIA driver (570+). |
| `cannot see a CUDA GPU` | Update the NVIDIA driver, then run `setup.bat` again. |
| `Ollama server ... not reachable` | Open the Ollama app from the Start menu, or just use `run.bat` (it starts Ollama). |
| A model download failed | Run `setup.bat` again; finished downloads are kept. |
| Very slow code generation | Another program is using the GPU; close games and video apps. |

## Manual setup (without the scripts)
```
uv sync
uv run playwright install chromium
uv run python setup_check.py --prefetch
uv run python harness.py "your idea" --open
```

## Tests (no GPU needed; mock Ollama / Stable Diffusion servers)
`uv run python tests/test_e2e.py` (40 checks) and `uv run python tests/test_mcp.py` (9 checks).

## Optional: external Forge instead of the built-in image generator
`set HARNESS_IMAGE_BACKEND=forge`, start Stable Diffusion Forge with `--api` (`uv run python setup_check.py --enable-forge-api --forge-dir "C:\path\to\Forge"`), then use `run.bat` as normal.
