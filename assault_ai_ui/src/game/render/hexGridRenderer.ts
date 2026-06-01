import * as PIXI from "pixi.js";

import {
  getTerrainColor,
  getTerrainLabel,
  getTerrainShort,
} from "../config/terrainConfig";

// ---------------------------------------------
export const HEX_SIZE = 30;

const HEX_WIDTH = HEX_SIZE * Math.sqrt(3);
const HEX_HEIGHT = HEX_SIZE * (3 / 2);

// ---------------------------------------------
export function axialToPixel(q: number, r: number) {
  return {
    x: HEX_WIDTH * (q + 0.5 * (r % 2)) + HEX_WIDTH / 2,
    y: HEX_HEIGHT * r,
  };
}


// ---------------------------------------------
function axialToLabel(q: number, r: number) {
  return `${String.fromCharCode(65 + q)}${r + 1}`;
}

export function formatCoords(q: number, r: number): string {
  return `[${axialToLabel(q, r)}]`;
}

// ---------------------------------------------
export function drawHex(
  g: PIXI.Graphics,
  x: number,
  y: number,
  size: number,
  fillColor?: number,
  fillAlpha: number = 1
) {
  const offset = Math.PI / 6;

  g.moveTo(
    x + size * Math.cos(offset),
    y + size * Math.sin(offset)
  );

  for (let i = 1; i <= 6; i++) {
    const angle = offset + (i * Math.PI) / 3;

    g.lineTo(
      x + size * Math.cos(angle),
      y + size * Math.sin(angle)
    );
  }

  g.closePath();

  if (fillColor !== undefined) {
    g.fill({ color: fillColor, alpha: fillAlpha });
  }

  g.stroke({
    width: 2,
    color: 0xffffff,
    alpha: 0.4,
  });
}

// ---------------------------------------------
export function drawHexGridBase(
  container: PIXI.Container,
  shape: [number, number],
  showCoords: boolean,
  hexes: { q: number; r: number; terrain: string }[] = [],
  showMap: boolean
) {
  const [width, height] = shape;

  const g = new PIXI.Graphics();
  container.sortableChildren = true;

  const terrainMap = new Map<number, string>();
  for (const h of hexes) {
    terrainMap.set(h.q * 100 + h.r, h.terrain);
  }

  // ---------------------------------------------
  // ✅ HOVER TEXT (FIX NÍTIDO)
  // ---------------------------------------------
  const hoverText = new PIXI.Text({
    text: "",
    style: {
      fill: "#ffffff",
      fontSize: 9,
      lineHeight: 12,
      dropShadow: {
        color: "#000000",
        alpha: 0.9,
        blur: 3,
        distance: 2,
      },
    },
    resolution: 2, // ✅ clave
  });

  hoverText.visible = false;
  hoverText.zIndex = 10;
  hoverText.eventMode = "none";
  hoverText.roundPixels = true; // ✅ CLAVE

  container.addChild(hoverText);

  const hoverHighlight = new PIXI.Graphics();
  hoverHighlight.zIndex = 4;
  container.addChild(hoverHighlight);

  const selectionHighlight = new PIXI.Graphics();
  selectionHighlight.zIndex = 6;
  container.addChild(selectionHighlight);

  const coordsLayer = new PIXI.Container();
  coordsLayer.zIndex = 3;
  container.addChild(coordsLayer);

  // ---------------------------------------------
  // GRID LOOP
  // ---------------------------------------------
  for (let r = 0; r < height; r++) {
    for (let q = 0; q < width; q++) {

      const { x, y } = axialToPixel(q, r);
      const px = Math.round(x);
      const py = Math.round(y + HEX_SIZE);

      const terrain = terrainMap.get(q * 100 + r) ?? "clear";

      if (!showMap) {
        drawHex(g, px, py, HEX_SIZE, getTerrainColor(terrain), 0.6);
      } else {
        drawHex(g, px, py, HEX_SIZE);
      }

      const coord = axialToLabel(q, r);
      const shortLabel = `${coord}\n${getTerrainShort(terrain)}`;
      const fullLabel = `${coord}\n${getTerrainLabel(terrain)}`;

      // ---------------------------------
      // ✅ GRID TEXT (FIX NÍTIDO)
      // ---------------------------------
      if (showCoords) {
        const text = new PIXI.Text({
          text: shortLabel,
          style: {
            fill: "#f5f5f5",
            fontSize: 9,
            lineHeight: 12,
            dropShadow: {
              color: "#000000",
              alpha: 0.7,
              blur: 2,
              distance: 1,
            },
          },
          resolution: 2, // ✅ clave
        });

        text.roundPixels = true; // ✅ CLAVE

        text.x = Math.round(px - HEX_SIZE * 0.6);
        text.y = Math.round(py - HEX_SIZE * 0.45);

        coordsLayer.addChild(text);
      }

      // ---------------------------------
      // ✅ HIT
      // ---------------------------------
      const hit = new PIXI.Graphics();

      hit.poly([
        px + HEX_SIZE * Math.cos(Math.PI / 6),
        py + HEX_SIZE * Math.sin(Math.PI / 6),
        px + HEX_SIZE * Math.cos(Math.PI / 2),
        py + HEX_SIZE * Math.sin(Math.PI / 2),
        px + HEX_SIZE * Math.cos(5 * Math.PI / 6),
        py + HEX_SIZE * Math.sin(5 * Math.PI / 6),
        px + HEX_SIZE * Math.cos(7 * Math.PI / 6),
        py + HEX_SIZE * Math.sin(7 * Math.PI / 6),
        px + HEX_SIZE * Math.cos(3 * Math.PI / 2),
        py + HEX_SIZE * Math.sin(3 * Math.PI / 2),
        px + HEX_SIZE * Math.cos(11 * Math.PI / 6),
        py + HEX_SIZE * Math.sin(11 * Math.PI / 6),
      ]);

      hit.fill({ color: 0xffffff, alpha: 0.001 });
      hit.eventMode = "static";
      hit.cursor = "pointer";

      // ---------------------------------
      // ✅ HOVER (FIX NÍTIDO)
      // ---------------------------------
      hit.on("pointerenter", () => {
        hoverText.text = fullLabel;

        hoverText.x = Math.round(px - HEX_SIZE * 0.6);
        hoverText.y = Math.round(py - HEX_SIZE * 0.45);

        hoverText.visible = true;

        hoverHighlight.clear();
        hoverHighlight.fill({ color: 0xffffff, alpha: 0.15 });
        hoverHighlight.stroke({ width: 2, color: 0xffffff });

        drawHex(hoverHighlight, px, py, HEX_SIZE);
      });

      hit.on("pointerleave", () => {
        hoverText.visible = false;
        hoverHighlight.clear();
      });

      // ---------------------------------
      // ✅ CLICK
      // ---------------------------------
      hit.on("pointerdown", () => {

        selectionHighlight.clear();

        selectionHighlight.fill({
          color: 0x3399ff,
          alpha: 0.25,
        });

        selectionHighlight.stroke({
          width: 3,
          color: 0x3399ff,
        });

        drawHex(selectionHighlight, px, py, HEX_SIZE);

        // 💣 AÑADE ESTE BLOQUE
        if ((window as any).onHexClick) {
          (window as any).onHexClick(q, r);
        }

      });


      container.addChild(hit);
    }
  }

  container.addChild(g);
}