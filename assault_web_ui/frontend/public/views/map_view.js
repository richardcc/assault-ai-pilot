// =================================================
// MAP VIEW
// Offset & scale test for hex map PNGs
// Grid has 16 rows
// Two map pieces:
//   - S3 starts at r = 0
//   - S2 starts at r = 8
// =================================================

window.renderMapView = function renderMapView() {

  let canvas = null;
  let ctx = null;
  let rafId = null;
  let detachMouse = null;

  // -------------------------------------------------
  // MAP IMAGES (OFFSET TEST MODE)
  // -------------------------------------------------
  const mapImageS3 = new Image();
  mapImageS3.src = "/public/art/maps/Map S3.png";

  const mapImageS2 = new Image();
  mapImageS2.src = "/public/art/maps/Map S2.png";

  // -------------------------------------------------
  // MAP PIECES (FIXED FOR NOW)
  // -------------------------------------------------
  const MAP_PIECES = [
    { image: mapImageS3, startRow: 0 }, // S3
    { image: mapImageS2, startRow: 8 }  // S2
  ];

  // -------------------------------------------------
  // Render loop
  // -------------------------------------------------
  function renderLoop() {
    rafId = requestAnimationFrame(renderLoop);
    render();
  }

  // -------------------------------------------------
  // Render
  // -------------------------------------------------
  function render() {
    if (
      !ctx ||
      !mapImageS3.complete ||
      !mapImageS2.complete
    ) return;

    // Reset canvas
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // =================================================
    // CAMERA (DO NOT TOUCH)
    // =================================================
    ctx.save();
    Camera2D.apply(ctx, canvas, UI_STATE.camera);

    // =================================================
    // GRID DATA
    // =================================================
    const { cols, rows } = GAME_STATE.scenario.map.grid;
    const R = HexGeometry.R;
    const DX = Math.sqrt(3) * R / 2;

    // -------------------------------------------------
    // Compute real grid bounding box (vertex-based)
    // -------------------------------------------------
    let xmin = Infinity, ymin = Infinity;
    let xmax = -Infinity, ymax = -Infinity;

    for (let r = 0; r < rows; r++) {
      for (let q = 0; q < cols; q++) {
        const { x, y } = HexGeometry.hexToPixel(q, r, 0, 0);

        const vertices = [
          { x: x,      y: y - R },
          { x: x + DX, y: y - R / 2 },
          { x: x + DX, y: y + R / 2 },
          { x: x,      y: y + R },
          { x: x - DX, y: y + R / 2 },
          { x: x - DX, y: y - R / 2 }
        ];

        for (const v of vertices) {
          xmin = Math.min(xmin, v.x);
          ymin = Math.min(ymin, v.y);
          xmax = Math.max(xmax, v.x);
          ymax = Math.max(ymax, v.y);
        }
      }
    }

    const gridWidthPx = xmax - xmin;

    // =================================================
    // MAP LOGIC
    // Each piece occupies rows / 2 = 8 hex rows
    // =================================================
    const mapRows = rows / 2;

    const logicalMapHeightPx =
      (mapRows - 1) * (1.5 * R) + 2 * R;

    // =================================================
    // SCALE (same scale for all pieces)
    // =================================================
    const scaleX = gridWidthPx / mapImageS3.width;
    const scaleY = logicalMapHeightPx / mapImageS3.height;

    // =================================================
    // DRAW MAP PIECES
    // =================================================
    for (const piece of MAP_PIECES) {
      const start = HexGeometry.hexToPixel(0, piece.startRow, 0, 0);
      const yOffset = start.y - R;

      ctx.save();
      ctx.translate(xmin, yOffset);
      ctx.scale(scaleX, scaleY);
      ctx.drawImage(piece.image, 0, 0);
      ctx.restore();
    }

    // =================================================
    // DRAW GRID (NAVY BLUE)
    // =================================================
    const hexes = [];
    for (let r = 0; r < rows; r++) {
      for (let q = 0; q < cols; q++) {
        const { x, y } = HexGeometry.hexToPixel(q, r, 0, 0);
        hexes.push({ q, r, x, y });
      }
    }

    ctx.strokeStyle = "rgba(11, 29, 58, 0.6)";
    ctx.lineWidth = 1;
    ctx.setLineDash([5, 4]);

    HexRender.drawDashedHexGrid(
      ctx,
      hexes.map(h => ({ x: h.x, y: h.y })),
      R
    );

    ctx.setLineDash([]);

    for (const h of hexes) {
      HexOverlay.drawHexCoords(
        ctx,
        h.q,
        h.r,
        h.x,
        h.y,
        R
      );
    }

    ctx.restore();
  }

  // -------------------------------------------------
  // Public API
  // -------------------------------------------------
  return {

    mount(container) {
      canvas = document.createElement("canvas");
      canvas.width  = container.clientWidth  || 800;
      canvas.height = container.clientHeight || 600;
      canvas.style.width = "100%";
      canvas.style.height = "100%";
      canvas.style.background = "#111";
      canvas.tabIndex = 0;

      container.innerHTML = "";
      container.appendChild(canvas);
      ctx = canvas.getContext("2d");

      detachMouse = MouseInput.attach(canvas, UI_STATE.camera);

      UI_STATE.camera.x = 0;
      UI_STATE.camera.y = 0;
      UI_STATE.camera.zoom = 1;
      UI_STATE.camera.rotation = 0;

      renderLoop();
    },

    dispose() {
      if (detachMouse) detachMouse();
      if (rafId) cancelAnimationFrame(rafId);
    }
  };
};