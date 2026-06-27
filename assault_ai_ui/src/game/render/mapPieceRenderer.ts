import * as PIXI from "pixi.js";
import { axialToPixel, HEX_SIZE } from "./hexGridRenderer";
import { getMapPieceImageCandidates } from "./mapPieceMapping";

// ---------------------------------------------
const HEX_WIDTH = HEX_SIZE * Math.sqrt(3);
const HEX_HEIGHT = HEX_SIZE * (3 / 2);

function normalizeQuarterTurns(rotationDeg: number): number {
  if (!Number.isFinite(rotationDeg)) return 0;
  if (rotationDeg % 90 !== 0) {
    console.warn(`Invalid map piece rotation ${rotationDeg}; expected multiple of 90.`);
    return 0;
  }
  return ((rotationDeg / 90) % 4 + 4) % 4;
}

// ---------------------------------------------
export async function drawMapPieces(
  container: PIXI.Container,
  pieces: any[]
) {
  for (const piece of pieces) {
    const textureCandidates = getMapPieceImageCandidates(piece.id);
    let texture: PIXI.Texture;
    let loadedPath: string | null = null;
    try {
      let loaded: PIXI.Texture | null = null;
      for (const path of textureCandidates) {
        try {
          loaded = await PIXI.Assets.load(path);
          loadedPath = path;
          break;
        } catch {
          // Try next candidate.
        }
      }
      if (!loaded) {
        throw new Error(`No texture candidate resolved for piece ${piece.id}`);
      }
      texture = loaded;
    } catch (err) {
      console.warn(
        `Map piece texture not found for ${piece.id}. Tried: ${textureCandidates.join(", ")}`,
        err
      );
      continue;
    }
    const sprite = new PIXI.Sprite(texture);
    // grid origin
    const [q, r] = piece.origin;
    const { x, y } = axialToPixel(q, r);

    const [hexW, hexH] = piece.shape;
    const quarterTurns = normalizeQuarterTurns(Number(piece.rotation ?? 0));

    console.log("PIECE:", piece);
    console.log("IMAGE:", piece.id, loadedPath);

    // Base size for an unrotated piece image.
    const baseWidth = (hexW + 0.5) * HEX_WIDTH;
    const baseHeight = (hexH - 1) * HEX_HEIGHT + HEX_SIZE * 2;

    const scaleX = baseWidth / texture.width;
    const scaleY = baseHeight / texture.height;

    sprite.scale.set(scaleX, scaleY);
    sprite.anchor.set(0, 0);
    sprite.rotation = quarterTurns * (Math.PI / 2);

    // Rotation is applied around top-left; compensate so the rotated bbox
    // starts at the same map origin cell.
    const rotationOffsetX =
      quarterTurns === 1 ? baseHeight :
      quarterTurns === 2 ? baseWidth :
      0;
    const rotationOffsetY =
      quarterTurns === 2 ? baseHeight :
      quarterTurns === 3 ? baseWidth :
      0;

    const offsetX = -HEX_WIDTH / 2;
    const offsetY = 0;
    sprite.x = x + offsetX + rotationOffsetX;
    sprite.y = y + offsetY + rotationOffsetY;

    container.addChild(sprite);
  }
}
