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

export function drawAttackIndicatorPixels(
  fromX: number,
  fromY: number,
  toX: number,
  toY: number,
  layer: PIXI.Container
) {
  const arrow = new PIXI.Graphics();
  const marker = new PIXI.Graphics();

  const dx = toX - fromX;
  const dy = toY - fromY;
  const len = Math.sqrt(dx * dx + dy * dy);
  if (len < 1) return;

  const angle = Math.atan2(dy, dx);
  const headLen = 16;

  arrow.setStrokeStyle({
    width: 3.5,
    color: 0xff4d4d,
    alpha: 0.95,
  });
  arrow.moveTo(fromX, fromY);
  arrow.lineTo(toX, toY);
  arrow.stroke();

  arrow.moveTo(toX, toY);
  arrow.lineTo(
    toX - headLen * Math.cos(angle - Math.PI / 6),
    toY - headLen * Math.sin(angle - Math.PI / 6)
  );
  arrow.stroke();

  arrow.moveTo(toX, toY);
  arrow.lineTo(
    toX - headLen * Math.cos(angle + Math.PI / 6),
    toY - headLen * Math.sin(angle + Math.PI / 6)
  );
  arrow.stroke();

  marker.circle(toX, toY, 18);
  marker.stroke({ width: 3, color: 0xff3333, alpha: 0.95 });
  marker.circle(toX, toY, 8);
  marker.fill({ color: 0xff3333, alpha: 0.45 });

  arrow.zIndex = 9999;
  marker.zIndex = 10000;

  layer.addChild(arrow);
  layer.addChild(marker);

  const pulseStart = performance.now();
  const pulseMs = 700;
  const tick = () => {
    const t = Math.min((performance.now() - pulseStart) / pulseMs, 1);
    const pulse = 1 + Math.sin(t * Math.PI * 3.5) * 0.12;
    marker.scale.set(pulse);
    const fade = 1 - t * 0.55;
    arrow.alpha = fade;
    marker.alpha = fade;
    if (t < 1) {
      requestAnimationFrame(tick);
    } else {
      arrow.destroy();
      marker.destroy();
    }
  };
  requestAnimationFrame(tick);
}
