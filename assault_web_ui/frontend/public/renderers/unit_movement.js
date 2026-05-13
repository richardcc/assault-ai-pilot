// -------------------------------------------------
// Unit Movement Animator
// -------------------------------------------------

const VISUAL_Y_OFFSET = () => HexGeometry.R * 0.02;

// -------------------------------------------------
// Movement sounds
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
// Position helpers
// -------------------------------------------------
function hexToWorld(q, r) {
  const p = HexGeometry.hexToPixel(q, r, 0, 0);
  return { x: p.x, y: p.y + VISUAL_Y_OFFSET() };
}

function snapUnitToHex(sprite, q, r) {
  const p = hexToWorld(q, r);
  sprite.x = p.x;
  sprite.y = p.y;
  sprite.__lastQ = q;
  sprite.__lastR = r;
}

// -------------------------------------------------
// Draw HEX
// -------------------------------------------------
function drawHexAt(q, r, grid, color, targetAlpha = 0.35) {
  const g = new PIXI.Graphics();
  const { x, y } = HexGeometry.hexToPixel(q, r, 0, 0);
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
  const from = HexGeometry.hexToPixel(fromQ, fromR, 0, 0);
  const to   = HexGeometry.hexToPixel(toQ, toR, 0, 0);

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
// Animate MOVEMENT
// -------------------------------------------------
function animateUnitMove(sprite, toHex, grid, ticker, duration, onComplete) {
  if (sprite.__lastQ === toHex.q && sprite.__lastR === toHex.r) {
    if (onComplete) onComplete();
    return;
  }

  const fromQ = sprite.__lastQ;
  const fromR = sprite.__lastR;

  sprite.__lastQ = toHex.q;
  sprite.__lastR = toHex.r;

  if (sprite.__moveTick) ticker.remove(sprite.__moveTick);

  const sound = window.moveSounds[Math.floor(Math.random() * window.moveSounds.length)];
  sound.cloneNode().play().catch(() => {});

  const layer = sprite.parent;

  const originHex = typeof fromQ === "number"
    ? drawHexAt(fromQ, fromR, grid, 0x3399ff, 0.3)
    : null;

  const destHex = drawHexAt(toHex.q, toHex.r, grid, 0x33cc66, 0.4);
  const arrow = typeof fromQ === "number"
    ? drawArrow(fromQ, fromR, toHex.q, toHex.r, grid)
    : null;

  if (originHex) layer.addChild(originHex);
  layer.addChild(destHex);
  if (arrow) layer.addChild(arrow);

  const start = { x: sprite.x, y: sprite.y };
  const end = hexToWorld(toHex.q, toHex.r);

  let elapsed = 0;

  function tick() {
    elapsed += ticker.elapsedMS;
    const t = Math.min(elapsed / duration, 1);
    const ease = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;

    sprite.x = start.x + (end.x - start.x) * ease;
    sprite.y = start.y + (end.y - start.y) * ease;

    const fade = Math.min(t * 3, 1);

    [originHex, destHex, arrow].forEach(o => {
      if (!o) return;
      o.alpha = fade * o.__targetAlpha;
    });

    if (t >= 1) {
      ticker.remove(tick);
      originHex?.destroy();
      destHex.destroy();
      arrow?.destroy();
      if (onComplete) onComplete();
    }
  }

  sprite.__moveTick = tick;
  ticker.add(tick);
}

// -------------------------------------------------
// ✅ Animate ATTACK (MISS / HIT / CRITICAL)
// -------------------------------------------------
// result: "MISS" | "HIT" | "CRITICAL"
function animateUnitAttack(
  attackerQ,
  attackerR,
  defenderQ,
  defenderR,
  grid,
  layer,
  ticker,
  duration = 800,
  result = "HIT",
  defenderSprite = null
) {
  const attackerHex = drawHexAt(attackerQ, attackerR, grid, 0xff4444, 0.35);
  const defenderHex = drawHexAt(defenderQ, defenderR, grid, 0xffd700, 0.45);

  const arrowColor = result === "MISS" ? 0x888888 : 0xffaa00;
  const arrowAlpha = result === "MISS" ? 0.35 : 0.6;
  const arrow = drawArrow(attackerQ, attackerR, defenderQ, defenderR, grid, arrowColor, arrowAlpha);

  layer.addChild(attackerHex);
  layer.addChild(defenderHex);
  layer.addChild(arrow);

  let elapsed = 0;
  let flashed = false;

  const doShake = result === "CRITICAL" && defenderSprite;
  const shakeAmp = doShake ? 2.5 : 0;
  const baseX = doShake ? defenderSprite.x : 0;

  function tick() {
    elapsed += ticker.elapsedMS;
    const t = Math.min(elapsed / duration, 1);

    const fadeIn  = Math.min(t * 3, 1);
    const fadeOut = Math.max((t - 0.7) / 0.3, 0);

    [attackerHex, defenderHex, arrow].forEach(o => {
      o.alpha = fadeOut === 0
        ? fadeIn * o.__targetAlpha
        : (1 - fadeOut) * o.__targetAlpha;
    });

    // Flash only for HIT / CRITICAL
    if (!flashed && t >= 0.45 && result !== "MISS") {
      flashed = true;
      const flashColor = result === "CRITICAL" ? 0xff5555 : 0xffffff;
      const flash = drawHexAt(defenderQ, defenderR, grid, flashColor, 0.9);
      layer.addChild(flash);
      setTimeout(() => flash.destroy(), 120);
    }

    // Shake only for CRITICAL
    if (doShake) {
      defenderSprite.x = baseX + Math.sin(t * 30) * shakeAmp;
    }

    if (t >= 1) {
      ticker.remove(tick);
      attackerHex.destroy();
      defenderHex.destroy();
      arrow.destroy();
      if (doShake) defenderSprite.x = baseX;
    }
  }

  ticker.add(tick);
}

// -------------------------------------------------
// API
// -------------------------------------------------
window.animateUnitMove   = animateUnitMove;
window.animateUnitAttack = animateUnitAttack;
window.snapUnitToHex     = snapUnitToHex;