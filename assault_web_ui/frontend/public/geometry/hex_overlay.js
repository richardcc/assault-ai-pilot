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
    ctx.font = "9px monospace";          // ✅ más pequeño
    ctx.textAlign = "left";
    ctx.textBaseline = "top";

    // Upper-left inside the hex, consistent with pointy-top
    const offsetX = -R * 0.62;
    const offsetY = -R * 0.62;

    ctx.fillText(
      `[${q},${r}]`,                     // ✅ corchetes
      cx + offsetX,
      cy + offsetY
    );

    ctx.restore();
  }

  return {
    drawHexCoords
  };

})();