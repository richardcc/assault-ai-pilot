// =================================================
// HEX RENDERING HELPERS
// Dashed hex grid rendering with edge deduplication
// Pointy-top hexes
// =================================================

const HexRender = (function () {

  // Compute the 6 vertices of a pointy-top hex
  function getHexPoints(cx, cy, R) {
    const pts = [];
    for (let i = 0; i < 6; i++) {
      const a = Math.PI / 3 * i - Math.PI / 2;
      pts.push({
        x: cx + R * Math.cos(a),
        y: cy + R * Math.sin(a)
      });
    }
    return pts;
  }

  // Create a stable key for an edge (order-independent)
  function edgeKey(p1, p2) {
    if (p1.x < p2.x || (p1.x === p2.x && p1.y <= p2.y)) {
      return `${p1.x},${p1.y}|${p2.x},${p2.y}`;
    }
    return `${p2.x},${p2.y}|${p1.x},${p1.y}`;
  }

  // -------------------------------------------------
  // Draw full dashed grid WITHOUT duplicated edges
  // -------------------------------------------------
  function drawDashedHexGrid(ctx, hexCenters, R) {
    const drawnEdges = new Set();

    ctx.beginPath();

    for (const { x, y } of hexCenters) {
      const pts = getHexPoints(x, y, R);

      for (let i = 0; i < 6; i++) {
        const p1 = pts[i];
        const p2 = pts[(i + 1) % 6];

        const key = edgeKey(p1, p2);
        if (drawnEdges.has(key)) continue;

        drawnEdges.add(key);
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
      }
    }

    ctx.stroke();
  }

  return {
    drawDashedHexGrid
  };

})();