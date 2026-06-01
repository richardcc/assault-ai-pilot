/**
 * combatFx.ts
 *
 * Implements combat projectile animations using PixiJS.
 * Draws flying dice representing attack and defense rolls.
 */

import * as PIXI from "pixi.js";
import { axialToPixel, HEX_SIZE } from "../render/hexGridRenderer";
import { soundService } from "../audio/SoundService";

const DIE_SIZE = 36;
const PROJECTILE_DURATION = 650;

function hexToPixelCenter(q: number, r: number) {
  const { x, y } = axialToPixel(q, r);
  return {
    x: x,
    y: y + HEX_SIZE,
  };
}

function getDieTexture(dieName: any): string {
  const name = String(dieName || "").toUpperCase();
  if (name.includes("CRITICAL")) {
    return "/assets/dice/red_03.png"; // Red die representing Critical
  } else if (name.includes("DAMAGE") || name.includes("HIT")) {
    return "/assets/dice/yellow_02.png"; // Yellow die representing Hit
  } else if (name.includes("DEFENSE") || name.includes("SHIELD")) {
    return "/assets/dice/blue_01.png"; // Blue die representing defense
  } else {
    return "/assets/dice/green_01.png"; // Green or default/miss die
  }
}

function getDieRollTexture(dieName: any): string {
  const name = String(dieName || "").toUpperCase();
  if (name.includes("CRITICAL")) {
    return "/assets/dice/red_00.png";
  } else if (name.includes("DAMAGE") || name.includes("HIT")) {
    return "/assets/dice/yellow_00.png";
  } else if (name.includes("DEFENSE") || name.includes("SHIELD")) {
    return "/assets/dice/blue_00.png";
  } else {
    return "/assets/dice/green_00.png";
  }
}

// -------------------------------------------------------------
// Play visual projectile animations for attack & defense dice
// -------------------------------------------------------------
export async function playCombatFX(
  fxLayer: PIXI.Container,
  attackerHex: { q: number; r: number },
  defenderHex: { q: number; r: number },
  attackDice: string[],
  defenseDice: string[]
): Promise<void> {

  console.log("🔥 playCombatFX", { attackerHex, defenderHex, attackDice, defenseDice });

  const attackerPos = hexToPixelCenter(attackerHex.q, attackerHex.r);
  const defenderPos = hexToPixelCenter(defenderHex.q, defenderHex.r);

  soundService.playAttack();
  fxLayer.sortableChildren = true;
  drawAttackArrow(fxLayer, attackerPos, defenderPos);

  const animations: Promise<void>[] = [];

  // 1. Process Attack Dice (fly from Attacker to Defender)
  attackDice.forEach((dieName, index) => {
    const startPos = {
      x: attackerPos.x + (index - attackDice.length / 2) * 15,
      y: attackerPos.y + (index % 2 === 0 ? -8 : 8),
    };
    const endPos = {
      x: defenderPos.x + (index - attackDice.length / 2) * 15,
      y: defenderPos.y + (index % 2 === 0 ? -8 : 8),
    };

    animations.push(
      animateSingleDie(
        fxLayer,
        startPos,
        endPos,
        getDieRollTexture(dieName),
        getDieTexture(dieName)
      )
    );
  });

  // 2. Process Defense Dice (fly from Defender to Attacker or burst locally)
  defenseDice.forEach((dieName, index) => {
    const startPos = {
      x: defenderPos.x + (index - defenseDice.length / 2) * 15,
      y: defenderPos.y + (index % 2 === 0 ? 8 : -8),
    };
    // Defense dice shield or deflect slightly outwards
    const endPos = {
      x: defenderPos.x + (index - defenseDice.length / 2) * 20 + (attackerPos.x > defenderPos.x ? 30 : -30),
      y: defenderPos.y + (index % 2 === 0 ? 20 : -20),
    };

    animations.push(
      animateSingleDie(
        fxLayer,
        startPos,
        endPos,
        getDieRollTexture(dieName),
        getDieTexture(dieName)
      )
    );
  });

  // Wait for all dice to complete their flight
  await Promise.all(animations);

  // Play impact flash at defender
  triggerImpactFlash(fxLayer, defenderPos);
}

// -------------------------------------------------------------
// Draw a temporary attack arrow from attacker to defender
// -------------------------------------------------------------
function drawAttackArrow(
  layer: PIXI.Container,
  from: { x: number; y: number },
  to: { x: number; y: number }
) {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const len = Math.sqrt(dx * dx + dy * dy);
  if (len < 1) return;

  const nx = dx / len;
  const ny = dy / len;
  const startGap = HEX_SIZE * 0.35;
  const endGap = HEX_SIZE * 0.5;
  const sx = from.x + nx * startGap;
  const sy = from.y + ny * startGap;
  const ex = to.x - nx * endGap;
  const ey = to.y - ny * endGap;

  const color = 0xff6666;
  const alpha = 0.95;
  const headLen = 16;
  const headAngle = Math.PI / 6;
  const angle = Math.atan2(dy, dx);

  const g = new PIXI.Graphics();
  g.lineStyle(3, color, alpha);
  g.moveTo(sx, sy);
  g.lineTo(ex, ey);

  g.moveTo(ex, ey);
  g.lineTo(
    ex - headLen * Math.cos(angle - headAngle),
    ey - headLen * Math.sin(angle - headAngle)
  );
  g.moveTo(ex, ey);
  g.lineTo(
    ex - headLen * Math.cos(angle + headAngle),
    ey - headLen * Math.sin(angle + headAngle)
  );

  g.beginFill(color, alpha);
  g.drawCircle(ex + nx * 5, ey + ny * 5, 4);
  g.endFill();

  g.zIndex = 9;
  layer.addChild(g);

  setTimeout(() => {
    if (!g.destroyed) {
      g.destroy();
    }
  }, 900);
}

// -------------------------------------------------------------
// Animate a single flying die using requestAnimationFrame
// -------------------------------------------------------------
function animateSingleDie(
  layer: PIXI.Container,
  from: { x: number; y: number },
  to: { x: number; y: number },
  rollTexturePath: string,
  finalTexturePath: string
): Promise<void> {
  return new Promise((resolve) => {
    const rollTexture = PIXI.Texture.from(rollTexturePath);
    const finalTexture = PIXI.Texture.from(finalTexturePath);
    const sprite = new PIXI.Sprite(rollTexture);
    sprite.anchor.set(0.5);
    sprite.x = from.x;
    sprite.y = from.y;
    sprite.width = DIE_SIZE;
    sprite.height = DIE_SIZE;
    sprite.zIndex = 10;

    layer.addChild(sprite);

    const startTime = performance.now();

    function tick() {
      const elapsed = performance.now() - startTime;
      const t = Math.min(elapsed / PROJECTILE_DURATION, 1);

      const ease = 1 - (1 - t) * (1 - t);

      sprite.x = from.x + (to.x - from.x) * ease;
      sprite.y = from.y + (to.y - from.y) * ease;
      sprite.rotation = t * Math.PI * 4 + elapsed / 120;

      if (t < 1) {
        requestAnimationFrame(tick);
      } else {
        sprite.texture = finalTexture;
        sprite.rotation = 0;

        setTimeout(() => {
          if (!sprite.destroyed) {
            sprite.destroy();
          }
          resolve();
        }, 700);
      }
    }

    requestAnimationFrame(tick);
  });
}

// -------------------------------------------------------------
// Draw impact circular explosion ring
// -------------------------------------------------------------
function triggerImpactFlash(layer: PIXI.Container, pos: { x: number; y: number }) {
  const g = new PIXI.Graphics();
  g.circle(0, 0, 12);
  g.fill({ color: 0xffaa00, alpha: 0.8 });
  g.x = pos.x;
  g.y = pos.y;

  layer.addChild(g);

  // Fade and clean up
  const start = performance.now();
  function fade() {
    const elapsed = performance.now() - start;
    const t = Math.min(elapsed / 250, 1);
    g.alpha = 1 - t;
    g.scale.set(1 + t * 1.5);
    if (t < 1) {
      requestAnimationFrame(fade);
    } else {
      g.destroy();
    }
  }
  requestAnimationFrame(fade);
}
