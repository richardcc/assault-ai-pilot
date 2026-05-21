import * as PIXI from "pixi.js";
import { axialToPixel } from "./hexGridRenderer";
import mapPieceMapping from "../data/map_piece_art_mapping.json";

// ---------------------------------------------
// CONFIG
// ---------------------------------------------
const HEX_SIZE = 30;

const HEX_WIDTH = HEX_SIZE * Math.sqrt(3);
const HEX_HEIGHT = HEX_SIZE * (3 / 2);
// ---------------------------------------------
// IMAGE OFFSET (tune this)
// ---------------------------------------------
const IMAGE_OFFSET_X = -HEX_WIDTH * 0.5;
const IMAGE_OFFSET_Y = -HEX_SIZE;

// ---------------------------------------------
// DRAW MAP PIECES
// ---------------------------------------------
export async function drawMapPieces(
  container: PIXI.Container,
  pieces: any[]
) {
  for (const piece of pieces) {

    const texturePath =
      mapPieceMapping.mapPieceImages[piece.id];

    if (!texturePath) {
      console.warn("Missing map piece:", piece.id);
      continue;
    }

    const texture = await PIXI.Assets.load(texturePath);

    const sprite = new PIXI.Sprite(texture);

    const [q, r] = piece.origin;

    const { x, y } = axialToPixel(q, r);

    // ---------------------------------------------
    // GET PIECE SIZE (IN HEX)
    // ---------------------------------------------
    const [hexWidthCount, hexHeightCount] =
      getPieceShape(piece.id);

    // ---------------------------------------------
    // TARGET SIZE IN PIXELS
    // ---------------------------------------------
    const targetWidth = (hexWidthCount + 0.5) * HEX_WIDTH;

    // IMPORTANT: height needs correction (hex overlap)
    const targetHeight =
      (hexHeightCount - 1) * HEX_HEIGHT + HEX_SIZE * 2;

    // ---------------------------------------------
    // SCALE IMAGE
    // ---------------------------------------------
    const scaleX = targetWidth / texture.width;
    const scaleY = targetHeight / texture.height;

    sprite.scale.set(scaleX, scaleY);

    // ---------------------------------------------
    // POSITION (snap to pixel)
    // ---------------------------------------------
    sprite.x = Math.round(x + IMAGE_OFFSET_X);
    sprite.y = Math.round(y + IMAGE_OFFSET_Y);

    // top-left alignment
    sprite.anchor.set(0, 0);

    container.addChild(sprite);
  }
}

// ---------------------------------------------
// PIECE SHAPE (TEMP → should come from backend)
// ---------------------------------------------
function getPieceShape(id: string): [number, number] {
  switch (id) {
    case "S2":
      return [9, 8];

    case "S3":
      return [9, 8];

    default:
      return [1, 1];
  }
}
``