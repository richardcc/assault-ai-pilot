import * as PIXI from "pixi.js";

// ---------------------------------------------
const HEX_SIZE = 30;

// ---------------------------------------------
// AXIAL → PIXEL (vertical offset layout)
// ---------------------------------------------
export function axialToPixel(q: number, r: number) {
  const x =
    HEX_SIZE * Math.sqrt(3) * (q + 0.5 * (r % 2));

  const y =
    HEX_SIZE * (3 / 2) * r;

  return { x, y };
}

// ---------------------------------------------
// DRAW SINGLE HEX (stroke only)
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

  // stroke only (no fill)
  g.stroke({
    width: 2,
    color: 0xffffff,
  });
}

// ---------------------------------------------
// DRAW FULL HEX GRID BASE (using shape)
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

      // snap to pixel to avoid rendering artifacts
      const px = Math.round(x);
      const py = Math.round(y);

      drawHex(g, px, py, HEX_SIZE);
    }
  }

  container.addChild(g);
}
