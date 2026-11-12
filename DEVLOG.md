# Devlog
- **Week 1** - Read the brief; decided on canvas JS + local models. Hand-made first test game with a generated ghost sprite to prove the asset path.
- **Forge setup** - hit missing libomp / torch DLL errors; switched to the cu121 torch 2.3.1 build (see DESIGN.md failures).
- **Sprite cut-out** - white box fix with rembg.
- **Harness build** (11 Nov) - planner, RAG, coder, sprites, music, assembler, headless tester, fix loop, MCP server; mock-server tests 38+9 passing.
- **Lab/PC run** - TODO: record measured results: time per game, pass rate on benchmark, fix rounds, VRAM peak.
- **Lessons** - pin GPU stack, post-process generated assets, test behaviour not just errors, fixed pipeline beats free agent for small models.
