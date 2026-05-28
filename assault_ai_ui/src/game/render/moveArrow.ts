import * as PIXI from "pixi.js";

export function drawMoveArrow(
  container: PIXI.Container,
  from: { x: number, y: number },
  to: { x: number, y: number },
  ticker?: PIXI.Ticker
) {
  const g = new PIXI.Graphics();

  const dx = to.x - from.x;
  const dy = to.y - from.y;

  const angle = Math.atan2(dy, dx);

  // ✅ línea principal
  g.moveTo(from.x, from.y);
  g.lineTo(to.x, to.y);
  g.stroke({ width: 4, color: 0x00ccff });

  // ✅ punta de flecha
  const size = 15;

  const left = {
    x: to.x - size * Math.cos(angle - Math.PI / 6),
    y: to.y - size * Math.sin(angle - Math.PI / 6)
  };

  const right = {
    x: to.x - size * Math.cos(angle + Math.PI / 6),
    y: to.y - size * Math.sin(angle + Math.PI / 6)
  };

  g.moveTo(to.x, to.y);
  g.lineTo(left.x, left.y);
  g.moveTo(to.x, to.y);
  g.lineTo(right.x, right.y);

  g.stroke({ width: 4, color: 0x00ccff });

  container.addChild(g);

  // 💣 animación opcional
  if (ticker) {
    let alive = true;

    const update = () => {
      if (!alive) return;

      g.alpha = 0.6 + Math.sin(Date.now() / 120) * 0.3;
    };

    ticker.add(update);

    // ✅ cleanup seguro (evita leaks y bugs raros)
    (g as any).__cleanup = () => {
      alive = false;
      ticker.remove(update);
    };
  }

  return g;
}