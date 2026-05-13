  // =================================================
  // HEX GRID LAYER (PIXI)
  // DEBUG STEP: draw grid + coordinates
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
      // Cleanup on re-init
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
      // Grid graphics (navy blue)
      // ---------------------------------------------
      const g = new PIXI.Graphics();
      g.lineStyle(1, 0x0b3d91, 0.9); // navy blue

      const R = HexGeometry.R;
      const HALF_W = HexGeometry.WIDTH / 2;

      let minX = Infinity;
      let minY = Infinity;
      let maxX = -Infinity;
      let maxY = -Infinity;

      // ---------------------------------------------
      // Text style for coordinates (DISCRETE DEBUG)
      // ---------------------------------------------
      const coordStyle = new PIXI.TextStyle({
        fontFamily: "monospace",
        fontSize: 9,          // ✅ MUCHO más adecuado
        fill: 0xff0000,
        letterSpacing: -1
      });

      // ---------------------------------------------
      // Draw grid + coordinates + bounds
      // ---------------------------------------------
      for (let r = 0; r < rows; r++) {
        for (let q = 0; q < cols; q++) {
          const { x, y } = HexGeometry.hexToPixel(q, r, 0, 0);

          // Hex
          drawHex(g, x, y, R);

          // Coordinates
          const label = new PIXI.Text(`[${q},${r}]`, coordStyle);

          // positioned inside upper-left area
          label.x = x - HALF_W * 0.65;
          label.y = y - R * 0.55;

          // ✅ evita que domine con el zoom
          label.resolution = 2;

          container.addChild(label);

          // Bounds
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

      // grid ON TOP of background, under text is fine for debug
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
