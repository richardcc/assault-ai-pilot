// renderer/highlight.js

import { HEX_R, hexToWorld } from "./grid.js";

/* ==========================================
   Internal helper: draw hex outline
   ========================================== */
function drawHexOutline(ctx, camera, col, row, color, lineWidth = 2) {
  if (col < 0 || row < 0) return;

  // ✅ SAVE CONTEXT STATE
  ctx.save();

  const { x, y } = hexToWorld(col, row);

  const sx = (x - camera.x) * camera.zoom;
  const sy = (y - camera.y) * camera.zoom;
  const r = HEX_R * camera.zoom;

  ctx.strokeStyle = color;
  ctx.lineWidth = lineWidth;

  const angles = [30, 90, 150, 210, 270, 330];
  ctx.beginPath();
  angles.forEach((a, i) => {
    const rad = (Math.PI / 180) * a;
    const px = sx + r * Math.cos(rad);
    const py = sy + r * Math.sin(rad);
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  });
  ctx.closePath();
  ctx.stroke();

  // ✅ RESTORE CONTEXT STATE
  ctx.restore();
}

/* ==========================================
   Public API
   ========================================== */

/** Red hex: origin of movement */
export function drawHexOrigin(ctx, camera, col, row) {
  drawHexOutline(ctx, camera, col, row, "#e63946", 3);
}

/** Green hex: destination of movement */
export function drawHexDestination(ctx, camera, col, row) {
  drawHexOutline(ctx, camera, col, row, "#2a9d8f", 3);
}

/** Yellow hex: active unit */
export function drawUnitHighlight(ctx, camera, col, row) {
  drawHexOutline(ctx, camera, col, row, "#ffd166", 4);
}