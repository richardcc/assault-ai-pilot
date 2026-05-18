// =================================================
// HEX GRID LAYER (PIXI)
// DEBUG STEP: draw grid + coordinates + TERRAIN
// =================================================

window.hexGridPixi = (function () {

  let container = null;
  let bounds = null;

  function init(world, scenario) {

    if (
      !scenario ||
      !scenario.map ||
      !scenario.map.grid ||
      typeof scenario.map.grid.cols !== "number" ||
      typeof scenario.map.grid.rows !== "number"
    ) {
      throw new Error("[HEX GRID] Invalid scenario.map.grid");
    }

    // ---------------------------------------------
    // ✅ TERRAIN MAP
    // ---------------------------------------------
    const terrainHexMap = new Map();

    if (scenario.map.hexes) {
      for (const h of scenario.map.hexes) {
        terrainHexMap.set(`${h.q},${h.r}`, h.terrain);
      }
    }

    // ---------------------------------------------
    // Cleanup
    // ---------------------------------------------
    if (container) {
      container.destroy({ children: true });
      container = null;
      bounds = null;
    }

    const { cols, rows } = scenario.map.grid;

    container = new PIXI.Container();
    world.addChild(container);

    // ---------------------------------------------
    // Grid graphics
    // ---------------------------------------------
    const g = new PIXI.Graphics();
    g.lineStyle(1, 0x0b3d91, 0.9);

    const R = HexGeometry.R;
    const HALF_W = HexGeometry.WIDTH / 2;

    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;

    // ---------------------------------------------
    // Styles
    // ---------------------------------------------
    const coordStyle = new PIXI.TextStyle({
      fontFamily: "monospace",
      fontSize: 10,
      fill: 0xff4444, // rojo (coords)
    });

    const terrainStyle = new PIXI.TextStyle({
      fontFamily: "monospace",
      fontSize: 8,     // 👈 MÁS PEQUEÑO
      fill: 0xffff66   // 👈 amarillo claro
    });

    // ---------------------------------------------
    // DRAW
    // ---------------------------------------------
    for (let r = 0; r < rows; r++) {
      for (let q = 0; q < cols; q++) {

        const { x, y } = HexGeometry.hexToPixel(q, r, 0, 0);

        // ✅ HEX BORDER
        drawHex(g, x, y, R);

        // ---------------------------------------------
        // ✅ COORDS (ARRIBA)
        // ---------------------------------------------
        const coordLabel = new PIXI.Text(
          `[${q},${r}]`,
          coordStyle
        );

        coordLabel.x = x - HALF_W * 0.65;
        coordLabel.y = y - R * 0.55;
        coordLabel.resolution = 2;

        container.addChild(coordLabel);

        // ---------------------------------------------
        // ✅ TERRAIN (ABAJO)
        // ---------------------------------------------
        const terrain = terrainHexMap.get(`${q},${r}`);

        if (terrain) {

          // 💡 opcional: simplificar nombre largo
          let short = terrain;

          if (terrain.includes("building")) short = "building";
          if (terrain === "light_forest") short = "forest";
          if (terrain === "olive_vine_grove") short = "grove";

          const terrainLabel = new PIXI.Text(
            short,
            terrainStyle
          );

          terrainLabel.anchor.set(0.5);
          terrainLabel.x = x;
          terrainLabel.y = y + R * 0.25;
          terrainLabel.resolution = 2;

          container.addChild(terrainLabel);
        }

        // ---------------------------------------------
        // bounds
        // ---------------------------------------------
        minX = Math.min(minX, x - HALF_W);
        maxX = Math.max(maxX, x + HALF_W);
        minY = Math.min(minY, y - R);
        maxY = Math.max(maxY, y + R);
      }
    }

    bounds = {
      x: minX,
      y: minY,
      width: maxX - minX,
      height: maxY - minY
    };

    container.addChild(g);

    console.log(
      `[HEX GRID] drawn ${cols}x${rows}`,
      bounds
    );
  }

  function drawHex(g, cx, cy, r) {
    const start = -Math.PI / 2;

    g.moveTo(cx + r * Math.cos(start), cy + r * Math.sin(start));

    for (let i = 1; i <= 6; i++) {
      const a = start + i * Math.PI / 3;
      g.lineTo(cx + r * Math.cos(a), cy + r * Math.sin(a));
    }

    g.closePath();
  }

  function getBounds() {
    return bounds;
  }

  return {
    init,
    getBounds
  };

})();
