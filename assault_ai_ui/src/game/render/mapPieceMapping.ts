const mapPieceImageOverrides: Record<string, string[]> = {
  S2: ["/art/maps/Map S2.png", "/art/maps/map_s2.png"],
  S3: ["/art/maps/Map S3.png", "/art/maps/map_s3.png"],
  S4: ["/art/maps/Map S4.png", "/art/maps/map_s4.png"],
  Z1: ["/art/maps/Map Z1.png", "/art/maps/map_z1.png"],
  Z2: ["/art/maps/Map Z2.png", "/art/maps/map_z2.png"],
};

export function getMapPieceImageCandidates(pieceId: string): string[] {
  const key = String(pieceId || "").toUpperCase();
  const mapped = mapPieceImageOverrides[key];
  if (mapped?.length) return mapped;

  const id = String(pieceId || "");
  const lowered = id.toLowerCase();
  return [
    `/art/maps/Map ${id}.png`,
    `/art/maps/map_${lowered}.png`,
  ];
}