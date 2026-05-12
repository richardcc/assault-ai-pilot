// =================================================
// MAP LAYER (PIXI)
// Renders the static map artwork inside a PIXI world
// =================================================

window.mapLayerPixi = (function () {

  let container = null;

  // -------------------------------------------------
  // INIT
  // -------------------------------------------------
  function init(worldContainer, mapUi) {
    container = new PIXI.Container();
    worldContainer.addChild(container);

    if (!mapUi || !mapUi.mapPieces || !mapUi.mapPieceImages) {
      console.error("[MAP LAYER PIXI] Missing map UI data");
      return;
    }

    let currentY = 0;

    // Draw map pieces from top to bottom
    for (const piece of mapUi.mapPieces) {
      const src = mapUi.mapPieceImages[piece.id];
      if (!src) {
        console.warn("[MAP LAYER PIXI] Missing image for piece:", piece.id);
        continue;
      }

      const texture = PIXI.Texture.from(src);
      const sprite = new PIXI.Sprite(texture);

      sprite.x = 0;
      sprite.y = currentY;

      container.addChild(sprite);
      currentY += sprite.height;
    }
  }

  // -------------------------------------------------
  // PUBLIC API
  // -------------------------------------------------
  return {
    init
  };
})();
