# Collectibles and power-ups
Kind: common
Keywords: collect, coins, stars, gems, pickup, power-up, powerup, shield, speed boost, magnet, bonus, treasure, food

Collectibles are objects that score when the player touches them. Power-ups set a timer that changes a rule until it runs out.

```javascript
let boostTimer = 0, shieldTimer = 0;
// when a power-up is touched:   boostTimer = 5; SFX.play('powerup');
// update(dt):
boostTimer = Math.max(0, boostTimer - dt);
const speed = boostTimer > 0 ? 420 : 260;               // speed boost while the timer runs
// shield: in hurtPlayer()      if (shieldTimer > 0) return;
// draw a timer bar:            ctx.fillStyle = '#44ddff'; ctx.fillRect(16, 48, 120 * (boostTimer / 5), 8);
// collectible with a bounce:   Sprites.draw(ctx, 'star', s.x, s.y + Anim.bob(Anim.time + s.phase, 5, 4), s.w, s.h);
```
Spawn collectibles at random positions inside the play area and remove them when collected. Win by collecting a target number: `if (score >= 20) { game.won = true; game.over = true; SFX.play('win'); }`.
