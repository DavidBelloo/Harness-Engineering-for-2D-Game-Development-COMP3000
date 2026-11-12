# Juice and animation: make it feel alive
Kind: common
Keywords: animation, animate, juice, polish, bob, wobble, squash, stretch, shake, particles, flash, spin, rotate, idle, feedback, effects

All animation is done with the helpers; no sprite sheets are needed.

```javascript
// idle bobbing:               Sprites.draw(ctx, 'hero', p.x, p.y + Anim.bob(Anim.time, 4, 5), p.w, p.h);
// breathing / pulsing:        const s = Anim.pulse(Anim.time, 0.06, 5);  Sprites.draw(ctx, 'coin', c.x, c.y, c.w, c.h, { scale: s });
// spinning:                   Sprites.draw(ctx, 'coin', c.x, c.y, c.w, c.h, { rotation: Anim.time * 4 });
// face movement direction:    Sprites.draw(ctx, 'hero', p.x, p.y, p.w, p.h, { flipX: p.vx < 0 });
// tilt while moving:          { rotation: Input.axisX() * 0.2 }
// hit flash:                  { flash: hurtTimer > 0 ? 0.7 : 0 }
// screen shake on big events: Anim.shake(10, 0.3);
// particle burst:             Particles.burst(x, y, { color: '#ffdd33', count: 12, speed: 180, life: 0.5, gravity: 300 });
// fading object:              { alpha: clamp(life / 0.5, 0, 1) }
```
Pair every important event (hit, pickup, shoot, win, lose) with `SFX.play(...)` and one visual effect.
