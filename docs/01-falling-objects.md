# Falling objects: dodge or catch
Kind: mechanic
Keywords: falling, dodge, avoid, catch, rain, drop, obstacles, pumpkins, meteors, fruit, bombs, spawn from top

Objects spawn above the screen at a random x and fall down. The player moves left/right along the bottom. Touching a bad object costs a life, touching a good one scores.

```javascript
let drops = [], dropTimer = 0;
function spawnDrop() {
  drops.push({ x: rand(0, W - 40), y: -40, w: 40, h: 40, vy: rand(150, 260), bad: Math.random() < 0.7 });
}
// in update(dt):
dropTimer -= dt;
if (dropTimer <= 0) { spawnDrop(); dropTimer = rand(0.4, 0.9); }
for (const d of drops) {
  d.y += d.vy * dt;
  if (rectsOverlap(player, d)) { d.dead = true; /* apply hit or score here */ }
  else if (d.y > H) d.dead = true;
}
drops = drops.filter(d => !d.dead);
```
Reset `drops = []` and `dropTimer = 0` in setup().
