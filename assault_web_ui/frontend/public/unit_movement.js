// -------------------------------------------------
// Unit Movement Animator (DEFINITIVE, BUG-FREE)
// -------------------------------------------------

// -------------------------------------------------
// Hex → World (consistent with map / renderer)
// -------------------------------------------------
function hexToWorld(q, r, grid) {
  return {
    x: q * grid.W + (r % 2) * (grid.W / 2),
    y: r * grid.ROW
  };
}

// -------------------------------------------------
// Movement sounds (dirt for now)
// -------------------------------------------------
const moveSounds = [
  new Audio("/public/assets/sfx/move/stepdirt_1.wav"),
  new Audio("/public/assets/sfx/move/stepdirt_2.wav"),
  new Audio("/public/assets/sfx/move/stepdirt_3.wav"),
  new Audio("/public/assets/sfx/move/stepdirt_4.wav"),
  new Audio("/public/assets/sfx/move/stepdirt_5.wav"),
  new Audio("/public/assets/sfx/move/stepdirt_6.wav"),
  new Audio("/public/assets/sfx/move/stepdirt_7.wav"),
  new Audio("/public/assets/sfx/move/stepdirt_8.wav")
];

// Volume tuning (safe default)
moveSounds.forEach(a => {
  a.volume = 0.35;
});

// -------------------------------------------------
// Animate ONE step — ALWAYS from current sprite pos
// -------------------------------------------------
function animateUnitMove(sprite, toHex, grid, app, duration, onComplete) {

  // ✅ Cancel previous movement if any
  if (sprite.__moveTick) {
    app.ticker.remove(sprite.__moveTick);
    sprite.__moveTick = null;
  }

  // 🔊 PLAY MOVE SOUND (once per movement)
  // Use a cloned node to allow overlapping moves safely
  const baseSound =
    moveSounds[Math.floor(Math.random() * moveSounds.length)];
  const sound = baseSound.cloneNode();
  sound.volume = baseSound.volume;
  sound.currentTime = 0;
  sound.play().catch(() => { /* ignore autoplay restrictions */ });

  const start = {
    x: sprite.x,
    y: sprite.y
  };

  const end = hexToWorld(toHex.q, toHex.r, grid);

  let elapsed = 0;

  function tick() {
    elapsed += app.ticker.elapsedMS;
    const t = Math.min(elapsed / duration, 1);

    // Heavy wargame easing (unchanged)
    const ease = t < 0.5
      ? 2 * t * t
      : 1 - Math.pow(-2 * t + 2, 2) / 2;

    sprite.x = start.x + (end.x - start.x) * ease;
    sprite.y = start.y + (end.y - start.y) * ease;

    if (t >= 1) {
      app.ticker.remove(tick);
      sprite.__moveTick = null;
      sprite.x = end.x;
      sprite.y = end.y;

      if (typeof onComplete === "function") {
        onComplete();
      }
    }
  }

  sprite.__moveTick = tick;
  app.ticker.add(tick);
}

// -------------------------------------------------
// Animate FULL PATH — sequential (not modified)
// -------------------------------------------------
function animateUnitPath(
  sprite,
  path,
  grid,
  app,
  stepDuration = 900,
  pause = 300
) {
  if (!Array.isArray(path) || path.length < 2) return;

  let index = 1;

  function next() {
    if (index >= path.length) return;

    animateUnitMove(
      sprite,
      path[index],
      grid,
      app,
      stepDuration,
      () => {
        index++;
        setTimeout(next, pause); // pause AFTER movement ends
      }
    );
  }

  next();
}

// -------------------------------------------------
// Public API
// -------------------------------------------------
window.animateUnitMove = animateUnitMove;
window.animateUnitPath = animateUnitPath;