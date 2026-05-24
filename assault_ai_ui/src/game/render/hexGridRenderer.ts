import * as PIXI from "pixi.js";

// ---------------------------------------------
// CONFIG
// ---------------------------------------------
export const HEX_SIZE = 30;

const HEX_WIDTH = HEX_SIZE * Math.sqrt(3);
const HEX_HEIGHT = HEX_SIZE * (3 / 2);

// ---------------------------------------------
// AXIAL → PIXEL (EVEN-R OFFSET ✅ CORRECTO)
// ---------------------------------------------
export function axialToPixel(q: number, r: number) {

  const x =
    HEX_WIDTH * (q + 0.5 * (r % 2)) + HEX_WIDTH / 2;

  const y =
    HEX_HEIGHT * r;

  return { x, y };
}


// ---------------------------------------------
// DRAW SINGLE HEX
// ---------------------------------------------
export function drawHex(
  g: PIXI.Graphics,
  x: number,
  y: number,
  size: number
) {
  const angleOffset = Math.PI / 6;

  g.moveTo(
    x + size * Math.cos(angleOffset),
    y + size * Math.sin(angleOffset)
  );

  for (let i = 1; i <= 6; i++) {
    const angle = angleOffset + (i * Math.PI) / 3;

    g.lineTo(
      x + size * Math.cos(angle),
      y + size * Math.sin(angle)
    );
  }

  g.closePath();

  g.stroke({
    width: 2,
    color: 0xffffff,
  });
}

// ---------------------------------------------
// DRAW GRID (RECTANGULAR SHAPE CORRECTO)
// ---------------------------------------------
export function drawHexGridBase(
  container: PIXI.Container,
  shape: [number, number]
) {
  const [width, height] = shape;

  const g = new PIXI.Graphics();

  for (let r = 0; r < height; r++) {
    for (let q = 0; q < width; q++) {

      const { x, y } = axialToPixel(q, r);

      drawHex(
        g,
        Math.round(x),
        Math.round(y + HEX_SIZE), // ✅ mantiene altura correcta
        HEX_SIZE
      );
    }
  }

  container.addChild(g);
}
