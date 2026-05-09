// -------------------------------------------------
// Map Renderer (FINAL – SIMPLE & CORRECT)
//
// Rules:
// - Grid defines geometry
// - S3 PNG starts at (grid minX, minY)
// - S2 PNG ends at (grid maxY)
// - No extra offsets or hacks
// - Camera handles pan + zoom
// -------------------------------------------------

function hexToWorld(q, r, grid) {
  const x = q * grid.W + (r % 2) * (grid.W / 2);
  const y = r * grid.ROW;
  return { x, y };
}

function computeGridBounds(hexes, grid) {
  let minX = Infinity, minY = Infinity;
  let maxX = -Infinity, maxY = -Infinity;

  hexes.forEach(h => {
    const p = hexToWorld(h.q, h.r, grid);
    minX = Math.min(minX, p.x - grid.W / 2);
    maxX = Math.max(maxX, p.x + grid.W / 2);
    minY = Math.min(minY, p.y - grid.R);
    maxY = Math.max(maxY, p.y + grid.R);
  });

  return { minX, minY, maxX, maxY };
}

function drawDashedHex(g, cx, cy, r) {
  const start = -Math.PI / 2;

  // Dash pattern (world units)
  const dash = 10;
  const gap  = 6;

  // Hex vertices
  const pts = [];
  for (let i = 0; i < 6; i++) {
    const a = start + (Math.PI / 3) * i;
    pts.push({
      x: cx + r * Math.cos(a),
      y: cy + r * Math.sin(a)
    });
  }

  // Draw each side dashed
  for (let i = 0; i < 6; i++) {
    const p0 = pts[i];
    const p1 = pts[(i + 1) % 6];

    const dx = p1.x - p0.x;
    const dy = p1.y - p0.y;
    const len = Math.hypot(dx, dy);

    const ux = dx / len;
    const uy = dy / len;

    let t = 0;
    let draw = true;

    while (t < len) {
      const seg = draw ? dash : gap;
      if (draw) {
        g.moveTo(
          p0.x + ux * t,
          p0.y + uy * t
        );
        g.lineTo(
          p0.x + ux * Math.min(t + seg, len),
          p0.y + uy * Math.min(t + seg, len)
        );
      }
      t += seg;
      draw = !draw;
    }
  }
}

function renderGrid(app, scenario) {

  const R   = scenario.grid.hexRadius;
  const W   = Math.sqrt(3) * R;
  const ROW = 1.5 * R;
  const grid = { R, W, ROW };

  const camera = new PIXI.Container();
  app.stage.addChild(camera);

  const bounds = computeGridBounds(scenario.map.hexes, grid);
  const worldWidth  = bounds.maxX - bounds.minX;
  const worldHeight = bounds.maxY - bounds.minY;

  // -------------------------------
  // MAP LAYER
  // -------------------------------
  const mapLayer = new PIXI.Container();
  camera.addChild(mapLayer);

  const rowsPerSection = scenario.map.height / 2;
  const sectionHeight = (rowsPerSection - 1) * ROW + 2 * R;

  // ---- S3 (TOP) → (grid.minX , grid.minY)
  {
    const tex = PIXI.Texture.from(scenario.pieces.S3.render.image);
    const spr = new PIXI.Sprite(tex);
    spr.scale.set(
      worldWidth / tex.width,
      sectionHeight / tex.height
    );
    spr.x = bounds.minX;
    spr.y = bounds.minY;
    mapLayer.addChild(spr);
  }

  // ---- S2 (BOTTOM) → (grid.minX , grid.maxY - sectionHeight)
  {
    const tex = PIXI.Texture.from(scenario.pieces.S2.render.image);
    const spr = new PIXI.Sprite(tex);
    spr.scale.set(
      worldWidth / tex.width,
      sectionHeight / tex.height
    );
    spr.x = bounds.minX;
    spr.y = bounds.maxY - sectionHeight;
    mapLayer.addChild(spr);
  }

  // -------------------------------
  // GRID OVERLAY
  // -------------------------------
  const g = new PIXI.Graphics();
  g.lineStyle({ width: 2, color: 0x0b1e3c, alpha: 0.85 });

  scenario.map.hexes.forEach(h => {
    const p = hexToWorld(h.q, h.r, grid);
    drawDashedHex(g, p.x, p.y, R);
  });

  camera.addChild(g);

  // -------------------------------
  // CAMERA FIT (unchanged)
  // -------------------------------
  const fit = Math.min(
    app.renderer.width  / worldWidth,
    app.renderer.height / worldHeight
  ) * 0.95;

  camera.scale.set(fit);
  camera.position.set(
    (app.renderer.width  - worldWidth  * fit) / 2 - bounds.minX * fit,
    (app.renderer.height - worldHeight * fit) / 2 - bounds.minY * fit
  );

  // -------------------------------
  // PAN + ZOOM (unchanged)
  // -------------------------------
  let dragging = false;
  let last = new PIXI.Point();

  app.stage.eventMode = "static";
  app.stage.hitArea = app.renderer.screen;

  app.stage.on("pointerdown", e => {
    dragging = true;
    last.copyFrom(e.global);
  });

  app.stage.on("pointerup", () => dragging = false);
  app.stage.on("pointerupoutside", () => dragging = false);

  app.stage.on("pointermove", e => {
    if (!dragging) return;
    camera.x += e.global.x - last.x;
    camera.y += e.global.y - last.y;
    last.copyFrom(e.global);
  });

  app.view.addEventListener(
    "wheel",
    e => {
      e.preventDefault();
      const factor = e.deltaY > 0 ? 0.9 : 1.1;
      camera.scale.set(
        Math.min(3, Math.max(0.3, camera.scale.x * factor))
      );
    },
    { passive: false }
  );
}

window.renderGrid = renderGrid;