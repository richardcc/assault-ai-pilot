import * as PIXI from "pixi.js";
import { axialToPixel, HEX_SIZE } from "../render/hexGridRenderer";

// -------------------------------------------------
// Unit Movement Animator
// -------------------------------------------------

const VISUAL_Y_OFFSET = () => HEX_SIZE * 0.02;

// -------------------------------------------------
// Movement sounds (GLOBAL SAFE)
// -------------------------------------------------

const moveSounds: HTMLAudioElement[] = [
  new Audio("/assets/sfx/move/stepdirt_1.wav"),
  new Audio("/assets/sfx/move/stepdirt_2.wav"),
  new Audio("/assets/sfx/move/stepdirt_3.wav"),
  new Audio("/assets/sfx/move/stepdirt_4.wav"),
  new Audio("/assets/sfx/move/stepdirt_5.wav"),
  new Audio("/assets/sfx/move/stepdirt_6.wav"),
  new Audio("/assets/sfx/move/stepdirt_7.wav"),
  new Audio("/assets/sfx/move/stepdirt_8.wav")
];

moveSounds.forEach(a => { a.volume = 0.35; });

// -------------------------------------------------
// Position helpers
// -------------------------------------------------
function hexToWorld(q: number, r: number) {
  const p = axialToPixel(q, r);
  return { x: p.x, y: p.y + HEX_SIZE + VISUAL_Y_OFFSET() };
}

export function snapUnitToHex(sprite: PIXI.Container, q: number, r: number) {
  const p = hexToWorld(q, r);
  sprite.x = p.x;
  sprite.y = p.y;
  (sprite as any).__lastQ = q;
  (sprite as any).__lastR = r;
}

// -------------------------------------------------
// Draw HEX
// -------------------------------------------------
function drawHexAt(q: number, r: number, color: number, alpha = 0.35) {
  const g = new PIXI.Graphics();

  const { x, y } = axialToPixel(q, r);
  const px = Math.round(x);
  const py = Math.round(y + HEX_SIZE);

  const size = HEX_SIZE;

  g.moveTo(
    px + size * Math.cos(Math.PI / 6),
    py + size * Math.sin(Math.PI / 6)
  );

  for (let i = 1; i <= 6; i++) {
    const angle = Math.PI / 6 + (i * Math.PI) / 3;

    g.lineTo(
      px + size * Math.cos(angle),
      py + size * Math.sin(angle)
    );
  }

  g.closePath();

  g.fill({ color, alpha });

  return g;
}

// -------------------------------------------------
// Draw ARROW
// -------------------------------------------------
function drawArrow(
  fromQ: number,
  fromR: number,
  toQ: number,
  toR: number,
  color = 0xffffff
) {
  const g = new PIXI.Graphics();

  const from = axialToPixel(fromQ, fromR);
  const to = axialToPixel(toQ, toR);

  const fx = Math.round(from.x);
  const fy = Math.round(from.y + HEX_SIZE);
  const tx = Math.round(to.x);
  const ty = Math.round(to.y + HEX_SIZE);

  const dx = tx - fx;
  const dy = ty - fy;
  const angle = Math.atan2(dy, dx);

  const headLen = 12;

  g.stroke({ width: 3, color });

  g.moveTo(fx, fy);
  g.lineTo(tx, ty);

  g.lineTo(
    tx - headLen * Math.cos(angle - Math.PI / 6),
    ty - headLen * Math.sin(angle - Math.PI / 6)
  );

  g.moveTo(tx, ty);
  g.lineTo(
    tx - headLen * Math.cos(angle + Math.PI / 6),
    ty - headLen * Math.sin(angle + Math.PI / 6)
  );

  return g;
}

// -------------------------------------------------
// Animate MOVEMENT
// -------------------------------------------------
export function animateUnitMove(
  sprite: PIXI.Container,
  toHex: { q: number; r: number },
  layer: PIXI.Container,
  duration = 400,
  onComplete?: () => void
) {
  const lastQ = (sprite as any).__lastQ;
  const lastR = (sprite as any).__lastR;

  if (lastQ === toHex.q && lastR === toHex.r) {
    onComplete?.();
    return;
  }

  (sprite as any).__lastQ = toHex.q;
  (sprite as any).__lastR = toHex.r;

  const sound =
    moveSounds[Math.floor(Math.random() * moveSounds.length)];
  (sound.cloneNode(true) as HTMLAudioElement).play().catch(() => {});

  const start = { x: sprite.x, y: sprite.y };
  const end = hexToWorld(toHex.q, toHex.r);

  const originHex =
    typeof lastQ === "number"
      ? drawHexAt(lastQ, lastR, 0x3399ff, 0.3)
      : null;

  const destHex = drawHexAt(toHex.q, toHex.r, 0x33cc66, 0.4);

  const arrow =
    typeof lastQ === "number"
      ? drawArrow(lastQ, lastR, toHex.q, toHex.r)
      : null;

  if (originHex) layer.addChild(originHex);
  layer.addChild(destHex);
  if (arrow) layer.addChild(arrow);

  let elapsed = 0;

  const ticker = PIXI.Ticker.shared;

  function tick(delta: any) {
    elapsed += ticker.deltaMS;
    const t = Math.min(elapsed / duration, 1);

    const ease =
      t < 0.5
        ? 2 * t * t
        : 1 - Math.pow(-2 * t + 2, 2) / 2;

    sprite.x = start.x + (end.x - start.x) * ease;
    sprite.y = start.y + (end.y - start.y) * ease;

    if (t >= 1) {
      ticker.remove(tick);
      originHex?.destroy();
      destHex.destroy();
      arrow?.destroy();
      onComplete?.();
    }
  }

  ticker.add(tick);
}

// -------------------------------------------------
// Animate ATTACK
// -------------------------------------------------
export function animateUnitAttack(
  attackerQ: number,
  attackerR: number,
  defenderQ: number,
  defenderR: number,
  layer: PIXI.Container,
  result: "MISS" | "HIT" | "CRITICAL" = "HIT"
) {
  const attackerHex = drawHexAt(attackerQ, attackerR, 0xff4444, 0.35);
  const defenderHex = drawHexAt(defenderQ, defenderR, 0xffd700, 0.45);

  const arrowColor = result === "MISS" ? 0x888888 : 0xffaa00;

  const arrow = drawArrow(
    attackerQ,
    attackerR,
    defenderQ,
    defenderR,
    arrowColor
  );

  layer.addChild(attackerHex);
  layer.addChild(defenderHex);
  layer.addChild(arrow);

  setTimeout(() => {
    attackerHex.destroy();
    defenderHex.destroy();
    arrow.destroy();
  }, 500);
}
