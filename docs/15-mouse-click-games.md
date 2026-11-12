# Mouse and click games: pop, whack, click targets
Kind: mechanic
Keywords: mouse, click, tap, pop, bubbles, whack, target, aim, point, cursor, clicker, balloons, mole, shooting gallery

Use `Input.mouse` ({x, y, down, pressed}). `pressed` is true only on the frame of the click. Test whether the click is inside a target with a point-in-rectangle check, and rise/float targets with dt.

```javascript
let bubbles, spawnTimer, missed;
// setup(): bubbles = []; spawnTimer = 0; missed = 0; score = 0; game.over = false;
// update(dt):
spawnTimer -= dt;
if (spawnTimer <= 0) { bubbles.push({ x: rand(40, W - 80), y: H + 10, w: 56, h: 56, vy: -rand(60, 140), wobble: rand(0, 6) }); spawnTimer = rand(0.4, 0.9); }
for (const b of bubbles) {
  b.y += b.vy * dt;
  b.x += Math.sin(Anim.time * 2 + b.wobble) * 30 * dt;
  if (Input.mouse.pressed && Input.mouse.x >= b.x && Input.mouse.x <= b.x + b.w && Input.mouse.y >= b.y && Input.mouse.y <= b.y + b.h) {
    b.dead = true; score += 1; SFX.play('pickup');
    Particles.burst(b.x + b.w / 2, b.y + b.h / 2, { color: '#aaddff', count: 10 });
  } else if (b.y < -b.h) { b.dead = true; missed += 1; SFX.play('hit'); if (missed >= 5) { game.over = true; SFX.play('gameover'); } }
}
bubbles = bubbles.filter(b => !b.dead);
// draw: Sprites.draw(ctx, 'bubble', b.x, b.y, b.w, b.h);   a crosshair: drawText(ctx, '+', Input.mouse.x, Input.mouse.y, { align: 'center', baseline: 'middle' });
```
Only one object should be hit per click: after a hit set `Input.mouse.pressed = false`.
