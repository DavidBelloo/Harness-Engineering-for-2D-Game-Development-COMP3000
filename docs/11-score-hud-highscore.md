# Score, HUD, combo and high score
Kind: common
Keywords: score, hud, ui, text, lives display, combo, multiplier, high score, best, timer display, interface, label

Draw the HUD last so it sits on top. `drawText` handles alignment and a shadow.

```javascript
let score, best = 0, combo;
// when scoring:   combo += 1; score += 10 * combo;       when hurt: combo = 0;
// when the game ends:  best = Math.max(best, score);     (do NOT reset `best` in setup())
// draw(ctx) at the end:
drawText(ctx, 'Score: ' + score, 16, 12);
drawText(ctx, 'Best: ' + best, 16, 44, { size: 18, color: '#cfd8ff' });
drawText(ctx, 'Lives: ' + lives, W - 16, 12, { align: 'right' });
if (combo > 1) drawText(ctx, 'x' + combo, W / 2, 12, { align: 'center', color: '#ffdd33' });
// lives as little sprites:  for (let i = 0; i < lives; i++) Sprites.draw(ctx, 'hero', W - 40 - i * 34, 48, 28, 28);
```
