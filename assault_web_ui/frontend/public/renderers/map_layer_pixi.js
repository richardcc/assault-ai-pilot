// =================================================
// MAP LAYER (PIXI)
// EXACT equivalent of legacy renderer (FIXED)
// =================================================

window.mapLayerPixi = (function () {

  let container = null;

  async function init(world, mapUi, gridBounds, grid) {

    if (!mapUi || mapUi.mapPieces.length !== 2) {
      console.error("[MAP PIXI] Invalid mapUi");
      return;
    }

    // ---------------------------------------------
    // Cleanup
    // ---------------------------------------------
    if (container) {
      container.destroy({ children: true });
    }

    container = new PIXI.Container();

    // ✅ Map MUST be under the grid
    world.addChildAt(container, 0);

    // ---------------------------------------------
    // Load textures
    // ---------------------------------------------
    const urls = mapUi.mapPieces.map(p => mapUi.mapPieceImages[p.id]);
    await PIXI.Assets.load(urls);

    // ---------------------------------------------
    // Geometry (SAME AS LEGACY RENDERER)
    // ---------------------------------------------
    const R   = HexGeometry.R;
    const ROW = 1.5 * R; // ✅ FIX: DO NOT use HexGeometry.ROW

    const worldWidth = gridBounds.width;

    const rowsPerPiece = grid.rows / 2;
    const pieceHeight =
      (rowsPerPiece - 1) * ROW + 2 * R;

    console.log("[MAP PIXI] DEBUG geometry", {
      R,
      ROW,
      rowsPerPiece,
      pieceHeight,
      worldWidth,
      gridBounds
    });

    // ---------------------------------------------
    // TOP PIECE (S3)
    // ---------------------------------------------
    {
      const piece = mapUi.mapPieces[0];
      const tex = PIXI.Texture.from(mapUi.mapPieceImages[piece.id]);
      const spr = new PIXI.Sprite(tex);

      spr.scale.set(
        worldWidth / tex.width,
        pieceHeight / tex.height
      );

      spr.x = gridBounds.x;
      spr.y = gridBounds.y;

      container.addChild(spr);

      console.log("[MAP PIXI] TOP sprite", {
        x: spr.x,
        y: spr.y,
        w: spr.width,
        h: spr.height
      });
    }

    // ---------------------------------------------
    // BOTTOM PIECE (S2)
    // ---------------------------------------------
    {
      const piece = mapUi.mapPieces[1];
      const tex = PIXI.Texture.from(mapUi.mapPieceImages[piece.id]);
      const spr = new PIXI.Sprite(tex);

      spr.scale.set(
        worldWidth / tex.width,
        pieceHeight / tex.height
      );

      spr.x = gridBounds.x;
      spr.y = gridBounds.y + gridBounds.height - pieceHeight;

      container.addChild(spr);

      console.log("[MAP PIXI] BOTTOM sprite", {
        x: spr.x,
        y: spr.y,
        w: spr.width,
        h: spr.height
      });
    }

    console.log("[MAP PIXI] ✅ Map rendered (legacy-equivalent)");
  }

  return { init };

})();