// =================================================
// MAP UI BUILDER
// =================================================

window.buildMapUi = function buildMapUi(gameState) {

  const uiMap = gameState.uiMetadata?.map;
  const scenarioMap = gameState.scenario?.map;

  if (!uiMap || !scenarioMap) {
    console.error("[MAP UI BUILDER] Map data missing");
    return null;
  }

  const pieces = scenarioMap.pieces;
  const images = {};

  pieces.forEach(piece => {
    const img = uiMap.mapPieceImages?.[piece.id];
    if (!img) {
      console.warn(
        "[MAP UI BUILDER] No image for map piece:",
        piece.id
      );
      return;
    }
    images[piece.id] = img;
  });

  return {
    mapPieces: pieces,
    mapPieceImages: images
  };
};