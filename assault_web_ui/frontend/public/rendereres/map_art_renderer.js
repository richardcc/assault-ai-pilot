// =================================================
// MAP ART RENDERER
// Paints illustrated map pieces under the grid
// =================================================

const MapArtRenderer = (function () {

  const imageCache = new Map();

  function getImage(src) {
    if (!imageCache.has(src)) {
      const img = new Image();
      img.src = src;
      imageCache.set(src, img);
    }
    return imageCache.get(src);
  }

  const OFFSETS = {
    S3: { x: 80, y: 80 },
    S2: { x: 80, y: 80 }
  };

  function render(ctx, pieces, mapUi) {

    console.log("✅ MapArtRenderer.render EXECUTING", pieces?.length);

    if (!pieces || !mapUi?.mapPieceImages) {
      console.warn("❌ Missing pieces or mapUi");
      return;
    }

    const images = mapUi.mapPieceImages;

    for (const piece of pieces) {
      const src = images[piece.id];
      const offset = OFFSETS[piece.id];
      if (!src || !offset) continue;

      const img = getImage(src);

      // ✅ DEBUG VISUAL: siempre dibuja algo
      ctx.fillStyle = "rgba(255,0,0,0.3)";
      ctx.fillRect(offset.x, offset.y, 300, 300);

      if (!img.complete) {
        console.log("⏳ Image still loading:", src);
        continue;
      }

      console.log("🖼️ Drawing piece", piece.id);
      ctx.drawImage(img, offset.x, offset.y);
    }
  }

  return { render };

})();
