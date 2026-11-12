# Enemy movement patterns
Kind: common
Keywords: enemy, ai, patrol, sine wave, zigzag, bounce, wander, homing, boss, movement pattern, monsters, ghosts

Simple patterns are enough. Store a per-enemy `phase` or direction and update it with dt.

```javascript
// sine wave (falls while swaying):   e.y += e.vy * dt;  e.x = e.baseX + Math.sin(Anim.time * 2 + e.phase) * 80;
// patrol left and right:             e.x += e.dir * e.speed * dt;  if (e.x < 0 || e.x > W - e.w) e.dir *= -1;
// bounce around the screen:          e.x += e.vx * dt; e.y += e.vy * dt;
//                                    if (e.x < 0 || e.x > W - e.w) e.vx *= -1;  if (e.y < 0 || e.y > H - e.h) e.vy *= -1;
// zig-zag:                           e.timer -= dt; if (e.timer <= 0) { e.vx = pick([-160, 160]); e.timer = rand(0.5, 1.2); } e.x += e.vx * dt;
// homing (slow chase):               const d = dist(e.x, e.y, player.x, player.y) || 1;
//                                    e.x += (player.x - e.x) / d * e.speed * dt;  e.y += (player.y - e.y) / d * e.speed * dt;
```
Give each enemy `baseX = x`, `phase = rand(0, 6.28)` and `dir = pick([-1, 1])` when spawning it.
