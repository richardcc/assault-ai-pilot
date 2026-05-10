// -------------------------------------------------
// Unit Movement Animator (STABLE + ORIGIN & DEST HIGHLIGHT + ARROW FADE)
// -------------------------------------------------

function hexToWorld(q, r, grid) {
  return {
    x: q * grid.W + (r % 2) * (grid.W / 2),
    y: r * grid.ROW
  };
}

// -------------------------------------------------
// Movement sounds (ORIGINAL, UNCHANGED)
// -------------------------------------------------
if (!window.moveSounds) {
  window.moveSounds = [
    new Audio("/public/assets/sfx/move/stepdirt_1.wav"),
    new Audio("/public/assets/sfx/move/stepdirt_2.wav"),
    new Audio("/public/assets/sfx/move/stepdirt_3.wav"),
    new Audio("/public/assets/sfx/move/stepdirt_4.wav"),
    new Audio("/public/assets/sfx/move/stepdirt_5.wav"),
    new Audio("/public/assets/sfx/move/stepdirt_6.wav"),
    new Audio("/public/assets/sfx/move/stepdirt_7.wav"),
    new Audio("/public/assets/sfx/move/stepdirt_8.wav")
  ];
  window.moveSounds.forEach(a => { a.volume = 0.35; });
}

// -------------------------------------------------
// Draw HEX
// -------------------------------------------------
function drawHexAt(q, r, grid, color, targetAlpha = 0.35) {
  const g = new PIXI.Graphics();
  const { x, y } = hexToWorld(q, r, grid);
  const R = grid.R;

  g.lineStyle(2, color, 0.9);
  g.beginFill(color, 1);
  g.alpha = 0;

  for (let i = 0; i < 6; i++) {
    const a = Math.PI / 3 * i + Math.PI / 6;
    const px = x + R * Math.cos(a);
    const py = y + R * Math.sin(a);
    if (i === 0) g.moveTo(px, py);
    else g.lineTo(px, py);
  }

  g.closePath();
  g.endFill();
  g.__targetAlpha = targetAlpha;
  return g;
}

// -------------------------------------------------
// Draw ARROW
// -------------------------------------------------
function drawArrow(fromQ, fromR, toQ, toR, grid, color = 0xffffff, targetAlpha = 0.6) {
  const g = new PIXI.Graphics();

  const from = hexToWorld(fromQ, fromR, grid);
  const to   = hexToWorld(toQ, toR, grid);

  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const angle = Math.atan2(dy, dx);
  const headLen = 14;

  g.lineStyle(3, color, 0.9);
  g.moveTo(from.x, from.y);
  g.lineTo(to.x, to.y);

  g.moveTo(to.x, to.y);
  g.lineTo(
    to.x - headLen * Math.cos(angle - Math.PI / 6),
    to.y - headLen * Math.sin(angle - Math.PI / 6)
  );
  g.moveTo(to.x, to.y);
  g.lineTo(
    to.x - headLen * Math.cos(angle + Math.PI / 6),
    to.y - headLen * Math.sin(angle + Math.PI / 6)
  );

  g.alpha = 0;
  g.__targetAlpha = targetAlpha;
  return g;
}

// -------------------------------------------------
// Animate ONE step
// -------------------------------------------------
function animateUnitMove(sprite, toHex, grid, app, duration, onComplete) {

  if (sprite.__lastQ === toHex.q && sprite.__lastR === toHex.r) {
    if (typeof onComplete === "function") onComplete();
    return;
  }

  const fromQ = sprite.__lastQ;
  const fromR = sprite.__lastR;

  sprite.__lastQ = toHex.q;
  sprite.__lastR = toHex.r;

  if (sprite.__moveTick) {
    app.ticker.remove(sprite.__moveTick);
    sprite.__moveTick = null;
  }

  const baseSound =
    window.moveSounds[Math.floor(Math.random() * window.moveSounds.length)];
  baseSound.cloneNode().play().catch(() => {});

  const layer = sprite.parent;

  const originHex =
    typeof fromQ === "number"
      ? drawHexAt(fromQ, fromR, grid, 0x3399ff, 0.3)
      : null;

  const destHex =
    drawHexAt(toHex.q, toHex.r, grid, 0x33cc66, 0.4);

  const arrow =
    typeof fromQ === "number"
      ? drawArrow(fromQ, fromR, toHex.q, toHex.r, grid, 0xffffff, 0.6)
      : null;

  if (originHex) layer.addChild(originHex);
  layer.addChild(destHex);
  if (arrow) layer.addChild(arrow);

  // ✅ GUARANTEE ARROW ON TOP
  if (arrow) layer.setChildIndex(arrow, layer.children.length - 1);

  const start = { x: sprite.x, y: sprite.y };
  const end   = hexToWorld(toHex.q, toHex.r, grid);
  let elapsed = 0;

  function tick() {
    elapsed += app.ticker.elapsedMS;
    const t = Math.min(elapsed / duration, 1);

    const ease = t < 0.5
      ? 2 * t * t
      : 1 - Math.pow(-2 * t + 2, 2) / 2;

    sprite.x = start.x + (end.x - start.x) * ease;
    sprite.y = start.y + (end.y - start.y) * ease;

    const fadeIn  = Math.min(t * 3, 1);
    const fadeOut = Math.max((t - 0.7) / 0.3, 0);

    const applyFade = o => {
      if (!o) return;
      o.alpha = fadeOut === 0
        ? fadeIn * o.__targetAlpha
        : (1 - fadeOut) * o.__targetAlpha;
    };

    applyFade(originHex);
    applyFade(destHex);
    applyFade(arrow);

    if (t >= 1) {
      app.ticker.remove(tick);
      sprite.__moveTick = null;

      if (originHex) {
        layer.removeChild(originHex);
        originHex.destroy();
      }
      layer.removeChild(destHex);
      destHex.destroy();
      if (arrow) {
        layer.removeChild(arrow);
        arrow.destroy();
      }

      if (typeof onComplete === "function") onComplete();
    }
  }

  sprite.__moveTick = tick;
  app.ticker.add(tick);
}

window.animateUnitMove = animateUnitMove;