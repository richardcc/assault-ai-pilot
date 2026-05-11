// =================================================
// UI METADATA LOADER
// Loads frontend-only metadata for presentation
// =================================================

window.loadUiMetadata = async function loadUiMetadata() {

  const [
    sides,
    controllers,
    unitCounters,
    mapPieceArt
  ] = await Promise.all([
    fetch("/public/ui_metadata/sides.json").then(r => r.json()),
    fetch("/public/ui_metadata/controllers.json").then(r => r.json()),
    fetch("/public/ui_metadata/units.json").then(r => r.json()),
    fetch("/public/ui_metadata/map_piece_art_mapping.json").then(r => r.json())
  ]);

  return {
    sides,
    controllers,
    units: unitCounters,

    // ✅ MAP UI (MISMO TIPO que units)
    map: mapPieceArt
  };
};