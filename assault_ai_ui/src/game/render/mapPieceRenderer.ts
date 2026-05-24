import * as PIXI from "pixi.js";
import { axialToPixel, HEX_SIZE } from "./hexGridRenderer";
import { mapPieceImages } from "./mapPieceMapping";

// ---------------------------------------------
const HEX_WIDTH = HEX_SIZE * Math.sqrt(3);
const HEX_HEIGHT = HEX_SIZE * (3 / 2);

// ---------------------------------------------
export async function drawMapPieces(
  container: PIXI.Container,
  pieces: any[]
) {
  for (const piece of pieces) {

    const texturePath = mapPieceImages[piece.id];
    if (!texturePath) continue;

    const texture = await PIXI.Assets.load(texturePath);
    const sprite = new PIXI.Sprite(texture);

    // grid origin
    const [q, r] = piece.origin;
    const { x, y } = axialToPixel(q, r);

    const [hexW, hexH] = piece.shape;

    // ✅ width FIX correcto (esto sí era clave)
    const targetWidth = (hexW + 0.5) * HEX_WIDTH;

    const targetHeight =
      (hexH - 1) * HEX_HEIGHT + HEX_SIZE * 2;

    const scaleX = targetWidth / texture.width;
    const scaleY = targetHeight / texture.height;

    sprite.scale.set(scaleX, scaleY);

    // ---------------------------------------------
    // ✅ ALIGNMENT FINAL CORRECTO
    // ---------------------------------------------

    // ✅ X YA CORRECTO (grid xmin = borde del hex)
    // ---------------------------------------------
    // ✅ CORRECT GRID ALIGNMENT (true Ymin)
    // ---------------------------------------------

    const offsetX = -HEX_WIDTH / 2;

    // ✅ EXACT MATCH WITH GRID RENDERING
    const offsetY = 0 ;

    sprite.x = x + offsetX;
    sprite.y = y + offsetY;


    sprite.anchor.set(0, 0);

    container.addChild(sprite);
  }
}
