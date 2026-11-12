# Lives, damage and invincibility frames
Kind: common
Keywords: lives, health, hp, damage, hurt, hit, invincible, invulnerable, game over, three hits, die, lose

Give the player a number of lives. After a hit, make them invincible for a short time so one overlap does not remove all lives in a few frames. Flash the sprite while invincible.

```javascript
let lives, invincible;
// setup(): lives = 3; invincible = 0; game.over = false;
function hurtPlayer() {
  if (invincible > 0 || game.over) return;
  lives -= 1;
  invincible = 1.2;
  SFX.play('hit');
  Anim.shake(8);
  Particles.burst(player.x + player.w / 2, player.y + player.h / 2, { color: '#ff4444' });
  if (lives <= 0) { game.over = true; SFX.play('gameover'); }
}
// update(dt): invincible = Math.max(0, invincible - dt);
// when a hazard overlaps the player:  if (rectsOverlap(player, hazard)) { hazard.dead = true; hurtPlayer(); }
// draw: Sprites.draw(ctx, 'hero', player.x, player.y, player.w, player.h, { flash: invincible > 0 ? 0.6 : 0, alpha: invincible > 0 && Math.floor(Anim.time * 12) % 2 ? 0.5 : 1 });
```
Always compare with `lives <= 0` (not `=== 0`) and always check `rectsOverlap` every frame.
