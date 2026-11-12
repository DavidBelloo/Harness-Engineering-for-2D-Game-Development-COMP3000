# Grid games: snake and tile movement
Kind: mechanic
Keywords: grid, snake, caterpillar, worm, growing longer, grows, eating, tail, trail, tile, cells, puzzle, step, turn based, maze, board, sokoban, tetris, blocks

Move in discrete steps with a step timer instead of every frame. Store positions as grid cells and convert to pixels when drawing.

```javascript
const CELL = 40, COLS = W / CELL, ROWS = H / CELL;      // 20 x 15
let snake, dir, nextDir, stepTimer, food;
// setup(): snake = [{ cx: 10, cy: 7 }]; dir = { x: 1, y: 0 }; nextDir = dir; stepTimer = 0; food = { cx: 15, cy: 7 };
// update(dt): read input into nextDir (never allow a direct reverse)
if (Input.pressed('left') && dir.x !== 1) nextDir = { x: -1, y: 0 };
if (Input.pressed('right') && dir.x !== -1) nextDir = { x: 1, y: 0 };
if (Input.pressed('up') && dir.y !== 1) nextDir = { x: 0, y: -1 };
if (Input.pressed('down') && dir.y !== -1) nextDir = { x: 0, y: 1 };
stepTimer -= dt;
if (stepTimer <= 0) {
  stepTimer = 0.12; dir = nextDir;
  const head = { cx: snake[0].cx + dir.x, cy: snake[0].cy + dir.y };
  if (head.cx < 0 || head.cy < 0 || head.cx >= COLS || head.cy >= ROWS || snake.some(s => s.cx === head.cx && s.cy === head.cy)) {
    game.over = true; SFX.play('gameover'); return;
  }
  snake.unshift(head);
  if (head.cx === food.cx && head.cy === food.cy) { score += 1; SFX.play('pickup'); food = { cx: randInt(0, COLS - 1), cy: randInt(0, ROWS - 1) }; }
  else snake.pop();
}
// draw: Sprites.draw(ctx, 'food', food.cx * CELL, food.cy * CELL, CELL, CELL);
```
