// renderer/grid_render.js

import { HEX_R, COLS, TOTAL_ROWS, hexToWorld } from "./grid.js";

export function drawGrid(ctx, camera) {
  ctx.strokeStyle = "#cccccc";
  const r = HEX_R * camera.zoom;

  for (let row = 0; row < TOTAL_ROWS; row++) {
    for (let col = 0; col < COLS; col++) {
      const { x, y } = hexToWorld(col, row);

      const sx = (x - camera.x) * camera.zoom;
      const sy = (y - camera.y) * camera.zoom;

      drawHex(ctx, sx, sy, r);
    }
  }
}

function drawHex(ctx, cx, cy, r) {
  const angles = [30, 90, 150, 210, 270, 330];
  ctx.beginPath();
  angles.forEach((a, i) => {
    const rad = (Math.PI / 180) * a;
    const px = cx + r * Math.cos(rad);
    const py = cy + r * Math.sin(rad);
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  });
  ctx.closePath();
  ctx.stroke();
}
