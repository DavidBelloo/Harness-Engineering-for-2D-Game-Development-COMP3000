# Top-down movement and chasing enemies
Kind: mechanic
Keywords: top down, topdown, maze, dungeon, walk, explore, chase, collect, adventure, 8 direction, rpg, zombie, escape

Move on both axes with `axisX` and `axisY`. Normalise diagonals so they are not faster. Enemies chase by moving toward the player each frame.

```javascript
// update(dt):
let dx = Input.axisX(), dy = Input.axisY();
const len = Math.hypot(dx, dy) || 1;
player.x = clamp(player.x + (dx / len) * 230 * dt, 0, W - player.w);
player.y = clamp(player.y + (dy / len) * 230 * dt, 0, H - player.h);
for (const e of enemies) {
  const ex = player.x - e.x, ey = player.y - e.y, d = Math.hypot(ex, ey) || 1;
  e.x += (ex / d) * e.speed * dt;
  e.y += (ey / d) * e.speed * dt;
}
// flip the player sprite to face the way they walk:
// Sprites.draw(ctx, 'hero', player.x, player.y, player.w, player.h, { flipX: facingLeft });
```
Keep `facingLeft = true` when `dx < 0` and `false` when `dx > 0`.
