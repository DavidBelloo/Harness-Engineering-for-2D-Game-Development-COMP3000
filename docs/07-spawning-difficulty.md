# Spawning and rising difficulty
Kind: common
Keywords: spawn, timer, difficulty, waves, harder, speed up, endless, survive, ramp, progression, level

Use a countdown timer for spawns and let both the spawn rate and the speed grow with the score or elapsed time. Cap the values so the game stays fair.

```javascript
let spawnTimer, elapsed;
// setup(): spawnTimer = 1; elapsed = 0;
// update(dt):
elapsed += dt;
const difficulty = 1 + elapsed / 30;                    // grows by 1 every 30 seconds
spawnTimer -= dt;
if (spawnTimer <= 0) {
  spawnEnemy(160 * Math.min(difficulty, 3));            // speed grows, capped at 3x
  spawnTimer = Math.max(0.3, 1.2 / difficulty);         // spawns get faster, never below 0.3 s
}
```
Spawn objects outside the visible area (y < 0, or x < 0 / x > W) so they never pop into existence on screen.
