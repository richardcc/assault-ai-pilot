// ======================================================
// PIXI COMBAT FX SYSTEM (FINAL MULTI-DICE + DUAL SIDES)
// ======================================================

window.playCombatFX = function (attackerId, defenderId, dice) {
  console.log("🔥 playCombatFX", attackerId, defenderId, dice);
  animateDiceProjectile(attackerId, defenderId, dice);
};

// ------------------------------------------------------
// PROJECTILE DICE
// ------------------------------------------------------
function animateDiceProjectile(attackerId, defenderId, dice) {

  const layer = window.fxLayer;

  if (!layer) {
    console.warn("fxLayer missing");
    return;
  }

  if (!window.getUnitHexPosition) {
    console.warn("getUnitHexPosition missing");
    return;
  }

  const attackerHex = window.getUnitHexPosition(attackerId);
  const defenderHex = window.getUnitHexPosition(defenderId);

  if (!attackerHex || !defenderHex) {
    console.warn("hex positions missing");
    return;
  }

  console.log("DICE COUNT:", dice.length);

  dice.forEach((die, i) => {

    // ✅ decide origin (attacker / defender)
    const isAttackerDie = die.side === "attacker";

    const originHex = isAttackerDie ? attackerHex : defenderHex;
    const targetHex = isAttackerDie ? defenderHex : attackerHex;

    const origin = hexToApproxWorld(originHex);
    const target = hexToApproxWorld(targetHex);

    const sprite = PIXI.Sprite.from(getDieTexture(die));
    sprite.anchor.set(0.5);

    // ✅ START OFFSET
    const startOffset = {
      x: (i - dice.length / 2) * 20,
      y: (i % 2 === 0 ? -10 : 10)
    };

    const startPos = {
      x: origin.x + startOffset.x,
      y: origin.y + startOffset.y
    };

    sprite.x = startPos.x;
    sprite.y = startPos.y;

    sprite.width = 40;
    sprite.height = 40;

    sprite.zIndex = 9999;

    layer.addChild(sprite);

    // ✅ TARGET OFFSET
    const endOffset = {
      x: (i - dice.length / 2) * 25,
      y: (i % 2 === 0 ? -15 : 15)
    };

    const targetPos = {
      x: target.x + endOffset.x,
      y: target.y + endOffset.y
    };

    // ✅ ANIMATION
    animateSimple(sprite, startPos, targetPos, 600, () => {
      impactEffect(sprite, targetPos);
    });

  });
}

// ------------------------------------------------------
// COORDINATE CONVERSION
// ------------------------------------------------------
function hexToApproxWorld(hex) {

  const originX = -25.98;
  const originY = -30;
  const size = 30;

  return {
    x:
      originX +
      hex.q * (Math.sqrt(3) * size) +
      (hex.r % 2) * (Math.sqrt(3) * size) / 2,

    y:
      originY +
      hex.r * (1.5 * size)
  };
}

// ------------------------------------------------------
// SIMPLE ANIMATION
// ------------------------------------------------------
function animateSimple(sprite, from, to, duration, onComplete) {

  const start = Date.now();

  function tick() {

    const t = (Date.now() - start) / duration;

    if (t >= 1) {
      sprite.x = to.x;
      sprite.y = to.y;

      if (onComplete) onComplete();
      return;
    }

    sprite.x = from.x + (to.x - from.x) * t;
    sprite.y = from.y + (to.y - from.y) * t;

    requestAnimationFrame(tick);
  }

  tick();
}

// ------------------------------------------------------
// IMPACT EFFECT + CLEANUP
// ------------------------------------------------------
function impactEffect(sprite, pos) {

  const g = new PIXI.Graphics();

  g.beginFill(0x00ff00);
  g.drawCircle(0, 0, 8);
  g.endFill();

  g.x = pos.x;
  g.y = pos.y;

  window.fxLayer.addChild(g);

  // ✅ remove effect
  setTimeout(() => {
    g.destroy();
  }, 200);

  // ✅ remove dice AFTER short delay
  setTimeout(() => {
    if (sprite && !sprite.destroyed) {
      sprite.destroy();
    }
  }, 1000);
}

// ------------------------------------------------------
// TEXTURE
// ------------------------------------------------------
function getDieTexture(die) {

  const color = (die?.color || "red").toLowerCase();
  return `/public/assets/dice/${color}_01.png`;
}