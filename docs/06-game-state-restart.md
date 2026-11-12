# Game state, game over, win and restart
Kind: common
Keywords: game over, restart, win, victory, state, reset, try again, title, end screen, lose condition, win condition

Everything that changes during play must be reset inside `setup()`. When the game ends set `game.over = true` (and `game.won = true` for a win), stop updating gameplay, and draw an overlay. Restart by calling `game.setup()`.

```javascript
// update(dt):
if (game.over) {
  if (Input.pressed('r') || Input.pressed('enter') || Input.pressed('space')) game.setup();
  return;                                     // freeze gameplay while the end screen shows
}
// ...normal gameplay below...

// draw(ctx), after drawing the scene:
if (game.over) {
  ctx.fillStyle = 'rgba(0,0,0,0.6)';
  ctx.fillRect(0, 0, W, H);
  drawText(ctx, game.won ? 'YOU WIN!' : 'GAME OVER', W / 2, H / 2 - 50, { size: 56, align: 'center' });
  drawText(ctx, 'Press R to restart', W / 2, H / 2 + 30, { align: 'center' });
}
```
When winning: `game.won = true; game.over = true; SFX.play('win');`.
