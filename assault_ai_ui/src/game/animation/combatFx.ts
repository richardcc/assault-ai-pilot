/**
 * combatFx.ts
 *
 * Implements combat projectile animations using PixiJS.
 * Draws flying dice representing attack and defense rolls.
 */

import * as PIXI from "pixi.js";
import { axialToPixel, HEX_SIZE } from "../render/hexGridRenderer";

const DIE_SIZE = 36;
const PROJECTILE_DURATION = 650;

function hexToPixelCenter(q: number, r: number) {
  const { x, y } = axialToPixel(q, r);
  return {
    x: x,
    y: y + HEX_SIZE,
  };
}

function getDieTexture(dieName: string): string {
  // Map dice string names (e.g. 'DAMAGE_01', 'CRITICAL_02', 'MISS') to local asset files
  const name = dieName.toUpperCase();
  if (name.includes("CRITICAL")) {
    return "/public/assets/dice/red_03.png"; // Red die representing Critical
  } else if (name.includes("DAMAGE") || name.includes("HIT")) {
    return "/public/assets/dice/yellow_02.png"; // Yellow die representing Hit
  } else if (name.includes("DEFENSE") || name.includes("SHIELD")) {
    return "/public/assets/dice/blue_01.png"; // Blue die representing defense
  } else {
    return "/public/assets/dice/green_01.png"; // Green or default/miss die
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
      animateSingleDie(fxLayer, startPos, endPos, getDieTexture(dieName))
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
      animateSingleDie(fxLayer, startPos, endPos, getDieTexture(dieName))
    );
  });

  // Wait for all dice to complete their flight
  await Promise.all(animations);

  // Play impact flash at defender
  triggerImpactFlash(fxLayer, defenderPos);
}

// -------------------------------------------------------------
// Animate a single flying die using requestAnimationFrame
// -------------------------------------------------------------
function animateSingleDie(
  layer: PIXI.Container,
  from: { x: number; y: number },
  to: { x: number; y: number },
  texturePath: string
): Promise<void> {
  return new Promise((resolve) => {
    const texture = PIXI.Texture.from(texturePath);
    const sprite = new PIXI.Sprite(texture);
    sprite.anchor.set(0.5);
    sprite.x = from.x;
    sprite.y = from.y;
    sprite.width = DIE_SIZE;
    sprite.height = DIE_SIZE;

    layer.addChild(sprite);

    const startTime = performance.now();

    function tick() {
      const elapsed = performance.now() - startTime;
      const t = Math.min(elapsed / PROJECTILE_DURATION, 1);

      // Quadratic easing out for smooth deceleration
      const ease = 1 - (1 - t) * (1 - t);

      sprite.x = from.x + (to.x - from.x) * ease;
      sprite.y = from.y + (to.y - from.y) * ease;
      sprite.rotation = t * Math.PI * 4; // Add dynamic spin

      if (t < 1) {
        requestAnimationFrame(tick);
      } else {
        // Impact burst particles can go here
        setTimeout(() => {
          if (!sprite.destroyed) {
            sprite.destroy();
          }
          resolve();
        }, 300);
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
