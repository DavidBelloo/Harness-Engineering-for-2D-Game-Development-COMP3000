# Design Document - Harness Engineering for 2D Game Development

## 1. Goal and constraints
Turn a one-sentence prompt into a playable 2D prototype with novel generated assets. No game engine, no frontier model in the harness, everything local on one 8GB GPU. The human writes no game code.

## 2. Components (code / art / animation / sfx / bgm / orchestration)
| Role | Choice | Why | Alternatives considered |
|---|---|---|---|
| Code | Qwen2.5-Coder 7B (Ollama) | fits 8GB, strong JS for size | larger models too big |
| Art | SD1.5 (Forge API) -> rembg -> crop -> pixelate (32 grid) -> 24-colour quantise | novel assets; pixelation hides diffusion noise | direct pixel-art models |
| Animation | `Anim`/`Particles` helpers (bob, pulse, shake, flash) in runtime | small models cannot invent animation from scratch; give them a vocabulary | sprite-sheet generation (unreliable) |
| SFX | Web Audio presets selected by the planner | zero VRAM, instant | AudioGen (extra VRAM/time) |
| BGM | MusicGen-small, 15 s, crossfaded loop | local, loops cleanly | chiptune fallback if unavailable |
| Orchestration | fixed Python pipeline + MCP server | reliable with a 7B model | free-form agent loop (see failures) |

## 3. Architecture
```
idea -> planner (JSON plan: title, sprites, sfx, controls)
     -> RAG (hybrid embeddings + BM25 over 15 pattern docs, mechanic quota)
     -> coder (skill prompt + patterns + plan) -> game.js
     -> unload LLM -> Forge sprites + background -> unload Forge -> MusicGen
     -> assemble: runtime-helpers.js + assets (base64) + game.js -> ONE html
     -> headless-browser test (scripted + random input) -> report -> LLM fix loop (max 3)
```
The "engine" is a ~300-line helper runtime (`skills/runtime-helpers.js`: input, sprite drawing, audio, particles, game loop). It is the harness's shared vocabulary, not a game engine: it has no physics, scene graph or editor, and the model writes all game logic.

**VRAM hand-off:** LLM, Stable Diffusion and MusicGen cannot co-reside in 8GB, so each stage ends by unloading its model (`keep_alive:0`, Forge `/unload-checkpoint`, freeing torch).

**Verification:** the checker plays the game in headless Chromium/Edge, reporting JS errors with the offending line of the model's code, blank or frozen canvas, sprites never drawn, and whether the game can end. That report is the fix-loop prompt.

## 4. Failed attempts and lessons learned
1. **Forge cu124 build crashed on Windows 11** (missing `libomp140.x86_64.dll`, fbgemm load failure). Fixed by using the `cu121_torch231` build. Lesson: pin the whole GPU stack; test it before building on top.
2. **`pip uninstall torch` hit system Python, not Forge's bundled Python.** Lesson: multiple Pythons - always check which interpreter is running.
3. **First game: white box around the sprite.** Raw diffusion output has a background. Fixed with rembg cut-out + flood-fill fallback. Lesson: generated assets need post-processing before use.
4. **Model-written games that "run" but are broken** (frozen or blank canvas, wrong sprite names). A syntax/no-error check is not enough; the checker now looks at pixels and drawn sprites. Lesson: test behaviour, not just errors.
5. **RAG retrieval crowded by generic docs** (lives/restart matched every idea) and missed "shooting" vs "shoot". Fixed with stemming, BM25 + curated keywords, and a quota reserving slots for genre docs with a relevance floor. Lesson: tune retrieval on real queries.
6. **Heavy dependencies avoided:** chromadb needs a C++ compiler on Windows; for 15 docs a numpy store is enough. mcp 2.x broke the API, so it is pinned `<2`.
7. **Free-form agent loop rejected** for the main path: a 7B model loses the thread; a fixed pipeline with LLM calls only where needed is far more reliable. MCP server kept for agentic use.

## 5. Evaluation
`python harness.py --batch prompts/benchmark.txt` runs 6 varied ideas and writes a table of pass/fail, time, fix rounds. (Insert measured numbers from the lab machine here.)

## 6. Limitations / next
Pixel quality depends on SD1.5 sprites; one level, single screen; 7B code quality varies by genre; no animation sheets.
