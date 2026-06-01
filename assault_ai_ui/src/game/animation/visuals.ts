import * as PIXI from "pixi.js";

export function drawArrowPixels(
  fromX: number,
  fromY: number,
  toX: number,
  toY: number,
  layer: PIXI.Container
) {
  const g = new PIXI.Graphics();

  const dx = toX - fromX;
  const dy = toY - fromY;
  const angle = Math.atan2(dy, dx);
  const headLen = 14;

  // ✅ Configurar estilo de trazo
  g.setStrokeStyle({
    width: 3,
    color: 0xffffff,
    alpha: 0.9
  });

  // ✅ Dibujar línea principal
  g.moveTo(fromX, fromY);
  g.lineTo(toX, toY);
  g.stroke();

  // ✅ Dibujar punta izquierda
  g.moveTo(toX, toY);
  g.lineTo(
    toX - headLen * Math.cos(angle - Math.PI / 6),
    toY - headLen * Math.sin(angle - Math.PI / 6)
  );
  g.stroke();

  // ✅ Dibujar punta derecha
  g.moveTo(toX, toY);
  g.lineTo(
    toX - headLen * Math.cos(angle + Math.PI / 6),
    toY - headLen * Math.sin(angle + Math.PI / 6)
  );
  g.stroke();

  g.alpha = 0.8;
  g.zIndex = 9999;

  layer.addChild(g);

  setTimeout(() => g.destroy(), 800);
}
