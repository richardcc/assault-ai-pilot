// =================================================
// HEX GEOMETRY
// Pointy-top hex grid (odd-r layout)
// Pure geometry utilities (NO rendering)
// =================================================

const HexGeometry = (function () {

  // -------------------------------------------------
  // Layout configuration
  // -------------------------------------------------
  const R = 30;                               // hex radius
  const WIDTH = Math.sqrt(3) * R;             // hex width
  const HEIGHT = 2 * R;                       // hex height

  const STEP_X = WIDTH;                      // horizontal spacing
  const STEP_Y = 1.5 * R;                    // vertical spacing

  // -------------------------------------------------
  // Convert hex (q, r) → pixel center
  // -------------------------------------------------
  function hexToPixel(q, r, originX = 0, originY = 0) {

    const x =
      originX +
      q * STEP_X +
      (r % 2) * (STEP_X / 2);

    const y =
      originY +
      r * STEP_Y;

    return { x, y };
  }

  // -------------------------------------------------
  // ✅ SAFE helper (used by FX directly)
  // -------------------------------------------------
  function hexToWorld(hex, origin) {

    if (!hex || hex.q === undefined || hex.r === undefined) {
      console.warn("⚠️ invalid hex → fallback");
      return { x: 300, y: 300 };
    }

    const originX = origin?.x ?? 0;
    const originY = origin?.y ?? 0;

    const p = hexToPixel(hex.q, hex.r, originX, originY);

    if (isNaN(p.x) || isNaN(p.y)) {
      console.warn("⚠️ NaN detected → fallback");
      return { x: 300, y: 300 };
    }

    return p;
  }

  // -------------------------------------------------
  // Compute world bounds of grid
  // -------------------------------------------------
  function computeGridBounds(cols, rows, originX, originY) {

    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;

    for (let r = 0; r < rows; r++) {
      for (let q = 0; q < cols; q++) {

        const { x, y } = hexToPixel(q, r, originX, originY);

        minX = Math.min(minX, x - WIDTH / 2);
        maxX = Math.max(maxX, x + WIDTH / 2);

        minY = Math.min(minY, y - R);
        maxY = Math.max(maxY, y + R);
      }
    }

    return { minX, minY, maxX, maxY };
  }

  // -------------------------------------------------
  // Compute grid center
  // -------------------------------------------------
  function computeGridCenter(cols, rows, originX, originY) {

    const first = hexToPixel(0, 0, originX, originY);
    const last = hexToPixel(cols - 1, rows - 1, originX, originY);

    return {
      x: (first.x + last.x) / 2,
      y: (first.y + last.y) / 2
    };
  }

  // -------------------------------------------------
  // ✅ GLOBAL EXPORT (IMPORTANTE)
  // -------------------------------------------------
  return {
    R,
    WIDTH,
    HEIGHT,
    STEP_X,
    STEP_Y,

    hexToPixel,
    hexToWorld,          // 🔥 NUEVO helper clave

    computeGridBounds,
    computeGridCenter
  };

})();

// ✅ exposición global (clave para FX)
window.HexGeometry = HexGeometry;