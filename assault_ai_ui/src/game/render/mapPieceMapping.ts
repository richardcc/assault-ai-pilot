const mapPieceImageOverrides: Record<string, string> = {
  S2: "/art/maps/Map S2.png",
  S3: "/art/maps/Map S3.png",
};

export function getMapPieceImage(pieceId: string): string {
  return mapPieceImageOverrides[pieceId] || `/art/maps/Map ${pieceId}.png`;
}