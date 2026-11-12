# Endless runner and scrolling background
Kind: mechanic
Keywords: runner, endless, scrolling, parallax, auto run, jump over, obstacles, lane, dash, flappy, side scroller

The world moves left while the player stays put. Obstacles spawn on the right edge and scroll toward the player. Jump with `Input.pressed('space')`.

```javascript
let scrollX, obstacles, spawnTimer, speed;
// setup(): scrollX = 0; obstacles = []; spawnTimer = 1; speed = 280;
// update(dt):
speed += 6 * dt;                                         // gets faster
scrollX += speed * dt;
spawnTimer -= dt;
if (spawnTimer <= 0) { obstacles.push({ x: W + 20, y: 500, w: 40, h: 50 }); spawnTimer = rand(0.9, 1.8); }
for (const o of obstacles) { o.x -= speed * dt; if (rectsOverlap(player, o)) { game.over = true; SFX.play('gameover'); } }
obstacles = obstacles.filter(o => o.x > -80);
score = Math.floor(scrollX / 10);
// ground strip that scrolls: for (let x = -(scrollX % 64); x < W; x += 64) ctx.fillRect(x, 550, 60, 50);
```
Use the platformer physics for the jump (gravity + `onGround`).
