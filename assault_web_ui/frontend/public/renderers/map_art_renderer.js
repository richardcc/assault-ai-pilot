function render(ctx, pieces, mapUi) {
  if (!pieces || !mapUi || !mapUi.mapPieceImages) return;

  let currentY = 0;

  for (const piece of pieces) {
    const src = mapUi.mapPieceImages[piece.id];
    if (!src) continue;

    const img = getImage(src);
    if (!img.complete) continue;

    // Dibujo de la imagen
    ctx.drawImage(img, 0, currentY);

    // 🟥 Línea roja debajo de cada mapa
    ctx.fillStyle = "red";
    ctx.fillRect(0, currentY + img.height - 5, img.width, 5);

    currentY += img.height;
  }
}