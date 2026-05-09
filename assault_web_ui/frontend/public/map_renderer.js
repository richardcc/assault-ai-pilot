// -------------------------------------------------
// Map Renderer (FINAL – SIMPLE & CORRECT)
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
  const pts = [];

  for (let i = 0; i < 6; i++) {
    const a = start + (Math.PI / 3) * i;
    pts.push({ x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) });
  }

  for (let i = 0; i < 6; i++) {
    g.moveTo(pts[i].x, pts[i].y);
    g.lineTo(pts[(i + 1) % 6].x, pts[(i + 1) % 6].y);
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

  const mapLayer = new PIXI.Container();
  camera.addChild(mapLayer);

  const rowsPerSection = scenario.map.height / 2;
  const sectionHeight = (rowsPerSection - 1) * ROW + 2 * R;

  // ---- S3 (TOP)
  {
    const tex = PIXI.Texture.from(scenario.pieces.S3.render.image);
    const spr = new PIXI.Sprite(tex);
    spr.scale.set(worldWidth / tex.width, sectionHeight / tex.height);
    spr.x = 0;
    spr.y = 0;
    mapLayer.addChild(spr);
  }

  // ---- S2 (BOTTOM)
  {
    const tex = PIXI.Texture.from(scenario.pieces.S2.render.image);
    const spr = new PIXI.Sprite(tex);
    spr.scale.set(worldWidth / tex.width, sectionHeight / tex.height);
    spr.x = 0;
    spr.y = sectionHeight;
    mapLayer.addChild(spr);
  }

  // ---- GRID
  const g = new PIXI.Graphics();
  g.lineStyle({ width: 1, color: 0x0b1e3c, alpha: 0.85 });

  scenario.map.hexes.forEach(h => {
    const p = hexToWorld(h.q, h.r, grid);
    drawDashedHex(g, p.x, p.y, R);
  });

  camera.addChild(g);

  // ---- CAMERA FIT
  const fit = Math.min(
    app.renderer.width  / worldWidth,
    app.renderer.height / worldHeight
  ) * 0.95;

  camera.scale.set(fit);
  camera.position.set(
    (app.renderer.width  - worldWidth  * fit) / 2 - bounds.minX * fit,
    (app.renderer.height - worldHeight * fit) / 2 - bounds.minY * fit
  );

  // ---- PAN + ZOOM (YA FUNCIONA)
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

  app.view.addEventListener("wheel", e => {
    e.preventDefault();
    const factor = e.deltaY > 0 ? 0.9 : 1.1;
    camera.scale.set(
      Math.min(3, Math.max(0.3, camera.scale.x * factor))
    );
  }, { passive: false });
}

window.renderGrid = renderGrid;