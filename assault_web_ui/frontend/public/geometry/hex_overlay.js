// =================================================
// HEX OVERLAY RENDERERS
// Debug/UI overlays for hex grids
// =================================================

const HexOverlay = (function () {

  /**
   * Draw [q,r] coordinates inside a hex (small, red)
   * Upper-left interior placement
   */
  function drawHexCoords(ctx, q, r, cx, cy, R) {
    ctx.save();

    ctx.fillStyle = "#ff2a2a";
    ctx.font = "9px monospace";
    ctx.textAlign = "left";
    ctx.textBaseline = "top";

    const offsetX = -R * 0.62;
    const offsetY = -R * 0.62;

    ctx.fillText(
      `[${q},${r}]`,
      cx + offsetX,
      cy + offsetY
    );

    ctx.restore();
  }

  /**
   * Draw a highlighted hex outline (for combat)
   * cx, cy : pixel center of hex
   * R      : hex radius
   * color  : stroke color
   */
  function drawHexHighlight(ctx, cx, cy, R, color) {
    const pts = [];

    for (let i = 0; i < 6; i++) {
      const a = Math.PI / 3 * i - Math.PI / 2;
      pts.push({
        x: cx + R * Math.cos(a),
        y: cy + R * Math.sin(a)
      });
    }

    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(pts[0].x, pts[0].y);
    for (let i = 1; i < pts.length; i++) {
      ctx.lineTo(pts[i].x, pts[i].y);
    }
    ctx.closePath();
    ctx.stroke();
    ctx.restore();
  }

  // ✅ Public API
  return {
    drawHexCoords,
    drawHexHighlight
  };

})();
