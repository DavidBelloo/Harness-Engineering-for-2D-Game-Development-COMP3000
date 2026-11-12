# Shooter: bullets, enemies and fire cooldown
Kind: mechanic
Keywords: shoot, shooter, bullets, lasers, enemies, space, ship, invaders, asteroids, fire, projectile, cooldown, blast

The player moves and fires bullets upward. Bullets and enemies are plain `{x, y, w, h}` objects. Use a cooldown so holding Space does not fire 60 bullets a second.

```javascript
let bullets = [], enemies = [], fireCooldown = 0, enemyTimer = 0;
// in update(dt):
fireCooldown -= dt;
if (Input.down('space') && fireCooldown <= 0) {
  bullets.push({ x: player.x + player.w / 2 - 6, y: player.y - 20, w: 12, h: 32, vy: -600 });
  fireCooldown = 0.22;
  SFX.play('shoot');
}
enemyTimer -= dt;
if (enemyTimer <= 0) { enemies.push({ x: rand(0, W - 48), y: -48, w: 48, h: 48, vy: rand(70, 140), hp: 1 }); enemyTimer = 0.9; }
for (const b of bullets) b.y += b.vy * dt;
for (const e of enemies) e.y += e.vy * dt;
for (const b of bullets) for (const e of enemies) {
  if (!b.dead && !e.dead && rectsOverlap(b, e)) {
    b.dead = true; e.hp -= 1;
    if (e.hp <= 0) { e.dead = true; score += 10; SFX.play('explosion'); Particles.burst(e.x + 24, e.y + 24, { color: '#ffaa33', count: 16 }); }
  }
}
for (const e of enemies) if (!e.dead && rectsOverlap(player, e)) { e.dead = true; /* player loses a life */ }
bullets = bullets.filter(b => !b.dead && b.y > -50);
enemies = enemies.filter(e => !e.dead && e.y < H + 50);
```
