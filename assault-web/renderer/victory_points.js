// renderer/victory_points.js

import { hexToWorld, HEX_R } from "./grid.js";

/**
 * Draw Victory Point hexes on the map
 * @param {CanvasRenderingContext2D} ctx
 * @param {Camera} camera
 * @param {Array} victoryPoints - [{ hex: "B4", owner: "IT" | "EN" | null }]
 */
export function drawVictoryPoints(ctx, camera, victoryPoints = []) {
  ctx.save();
  ctx.globalAlpha = 0.35;

  for (const vp of victoryPoints) {
    if (!vp.hex) continue;

    const { x, y } = hexToWorld(vp.hex[0], vp.hex[1]);
    const sx = (x - camera.x) * camera.zoom;
    const sy = (y - camera.y) * camera.zoom;
    const r = HEX_R * camera.zoom;

    // Color by control
    let color = "#cccc00"; // neutral (yellow)
    if (vp.owner === "IT") color = "#0044cc";
    if (vp.owner === "EN") color = "#cc0000";

    ctx.fillStyle = color;

    ctx.beginPath();
    const angles = [30, 90, 150, 210, 270, 330];
    angles.forEach((a, i) => {
      const rad = (Math.PI / 180) * a;
      const px = sx + r * 0.85 * Math.cos(rad);
      const py = sy + r * 0.85 * Math.sin(rad);
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    });
    ctx.closePath();
    ctx.fill();
  }

  ctx.restore();
}