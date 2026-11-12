# Platformer: gravity, jumping and platforms
Kind: mechanic
Keywords: platformer, jump, gravity, platforms, run, mario, side scrolling, ground, ledge, climb, hop

Use a velocity `vy` pulled down by gravity each frame. Only allow a jump when standing on something. Resolve vertical collisions against platforms (landing only when falling).

```javascript
let player, platforms;
// setup():
player = { x: 80, y: 300, w: 40, h: 48, vx: 0, vy: 0, onGround: false };
platforms = [{ x: 0, y: 540, w: W, h: 60 }, { x: 200, y: 430, w: 160, h: 20 }, { x: 460, y: 330, w: 160, h: 20 }];
// update(dt):
player.vx = Input.axisX() * 260;
player.x = clamp(player.x + player.vx * dt, 0, W - player.w);
player.vy += 1400 * dt;                         // gravity
if (Input.pressed('space') || Input.pressed('up')) { if (player.onGround) { player.vy = -620; SFX.play('jump'); } }
const prevBottom = player.y + player.h;
player.y += player.vy * dt;
player.onGround = false;
for (const p of platforms) {
  if (rectsOverlap(player, p) && player.vy >= 0 && prevBottom <= p.y + 12) {
    player.y = p.y - player.h; player.vy = 0; player.onGround = true;
  }
}
if (player.y > H + 100) { game.over = true; }   // fell into the pit
```
Draw platforms with `ctx.fillRect(p.x, p.y, p.w, p.h)` and the player with `Sprites.draw`.
