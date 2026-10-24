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

const DICE_SPRITE_MAP: Record<string, Record<string, string>> = {
  BLUE: {
    "": "/assets/dice/blue_01.png",
    DAMAGE: "/assets/dice/blue_02.png",
    DEFENSE: "/assets/dice/blue_01.png",
    SHIELD: "/assets/dice/blue_01.png",
  },
  GREEN: {
    "": "/assets/dice/green_01.png",
    DAMAGE: "/assets/dice/green_02.png",
    "CRITICAL+DAMAGE": "/assets/dice/green_03.png",
    DEFENSE: "/assets/dice/green_01.png",
    SHIELD: "/assets/dice/green_01.png",
  },
  RED: {
    "": "/assets/dice/red_02.png",
    DAMAGE: "/assets/dice/red_01.png",
    "DAMAGE+DAMAGE": "/assets/dice/red_03.png",
    "CRITICAL+DAMAGE": "/assets/dice/red_04.png",
    CRITICAL: "/assets/dice/red_04.png",
  },
  YELLOW: {
    "": "/assets/dice/yellow_01.png",
    DAMAGE: "/assets/dice/yellow_02.png",
    "DAMAGE+DAMAGE": "/assets/dice/yellow_03.png",
    "CRITICAL+DAMAGE": "/assets/dice/yellow_04.png",
    CRITICAL: "/assets/dice/yellow_04.png",
  },
};

function parseDieInfo(dieInput: any): { color: string; face: string } {
  if (!dieInput) return { color: "RED", face: "DAMAGE" };
  if (typeof dieInput === "string") {
    const s = dieInput.toUpperCase();
    if (s.includes("BLUE") || s.includes("DEFENSE") || s.includes("SHIELD")) {
      return { color: "BLUE", face: s.includes("DAMAGE") ? "DAMAGE" : "SHIELD" };
    }
    if (s.includes("YELLOW")) {
      return { color: "YELLOW", face: s.includes("CRITICAL") ? "CRITICAL+DAMAGE" : "DAMAGE" };
    }
    if (s.includes("GREEN")) {
      return { color: "GREEN", face: s.includes("CRITICAL") ? "CRITICAL+DAMAGE" : "DAMAGE" };
    }
    if (s.includes("CRITICAL")) {
      return { color: "RED", face: "CRITICAL+DAMAGE" };
    }
    return { color: "RED", face: "DAMAGE" };
  }
  const color = String(dieInput?.color || "RED").toUpperCase();
  const faces = Array.isArray(dieInput?.faces)
    ? dieInput.faces.join("+").toUpperCase()
    : String(dieInput?.face || dieInput?.name || "").toUpperCase();
  return { color, face: faces };
}

function getDieTexture(dieInput: any): string {
  const { color, face } = parseDieInfo(dieInput);
  const colorMap = DICE_SPRITE_MAP[color] || DICE_SPRITE_MAP["RED"];
  if (colorMap[face]) return colorMap[face];
  if (face.includes("CRITICAL") && colorMap["CRITICAL+DAMAGE"]) return colorMap["CRITICAL+DAMAGE"];
  if (face.includes("DAMAGE") && colorMap["DAMAGE"]) return colorMap["DAMAGE"];
  if (face.includes("SHIELD") && colorMap["SHIELD"]) return colorMap["SHIELD"];
  if (face.includes("DEFENSE") && colorMap["DEFENSE"]) return colorMap["DEFENSE"];
  return colorMap[""] || "/assets/dice/red_01.png";
}

function getDieRollTexture(dieInput: any): string {
  const { color } = parseDieInfo(dieInput);
  switch (color) {
    case "BLUE":
      return "/assets/dice/blue_00.png";
    case "YELLOW":
      return "/assets/dice/yellow_00.png";
    case "GREEN":
      return "/assets/dice/green_00.png";
    case "RED":
    default:
      return "/assets/dice/red_00.png";
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
