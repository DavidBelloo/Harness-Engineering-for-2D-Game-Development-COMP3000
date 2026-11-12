# Time limits and win conditions
Kind: common
Keywords: timer, countdown, time limit, survive, win, goal, level complete, objective, race, clock, seconds

Count a clock down with `dt`. Win by surviving until it reaches zero or by reaching an objective; lose when time runs out first.

```javascript
let timeLeft;
// setup(): timeLeft = 45;
// update(dt):
timeLeft -= dt;
if (timeLeft <= 0) {
  timeLeft = 0; game.over = true;
  if (score >= 15) { game.won = true; SFX.play('win'); } else { SFX.play('gameover'); }
}
// draw: drawText(ctx, 'Time: ' + Math.ceil(timeLeft), W / 2, 12, { align: 'center', color: timeLeft < 10 ? '#ff6666' : '#ffffff' });
```
Survival games: `timeLeft` counts down and the player WINS when it hits 0 if they still have lives.
