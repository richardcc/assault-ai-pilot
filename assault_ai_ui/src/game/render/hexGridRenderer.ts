import * as PIXI from "pixi.js";

import {
  getTerrainColor,
  getTerrainLabel,
  getTerrainShort,
} from "../config/terrainConfig";
import {
  getFortificationArt,
  getFortificationRender,
  getFortificationShort,
} from "../config/fortificationConfig";
import { sides } from "../config/sides";

// ---------------------------------------------
export const HEX_SIZE = 30;

const HEX_WIDTH = HEX_SIZE * Math.sqrt(3);
const HEX_HEIGHT = HEX_SIZE * (3 / 2);
const fortTextureCache = new Map<string, PIXI.Texture>();
const fortTextureLoading = new Set<string>();
const fortTexturePromises = new Map<string, Promise<PIXI.Texture>>();
const sideMarkerTextureCache = new Map<string, PIXI.Texture>();
const sideMarkerTexturePromises = new Map<string, Promise<PIXI.Texture>>();

function getFortTexture(path: string): PIXI.Texture | null {
  const cached = fortTextureCache.get(path);
  if (cached) return cached;

  if (!fortTextureLoading.has(path)) {
    fortTextureLoading.add(path);
    void PIXI.Assets.load(path)
      .then((tex) => {
        fortTextureCache.set(path, tex);
      })
      .catch(() => {
        // fallback marker will be used
      })
      .finally(() => {
        fortTextureLoading.delete(path);
      });
  }
  return null;
}

function loadFortTexture(path: string): Promise<PIXI.Texture> {
  const cached = fortTextureCache.get(path);
  if (cached) return Promise.resolve(cached);

  const existing = fortTexturePromises.get(path);
  if (existing) return existing;

  const p = PIXI.Assets.load(path)
    .then((tex) => {
      fortTextureCache.set(path, tex);
      fortTextureLoading.delete(path);
      return tex;
    })
    .catch((err) => {
      fortTextureLoading.delete(path);
      throw err;
    })
    .finally(() => {
      fortTexturePromises.delete(path);
    });

  fortTextureLoading.add(path);
  fortTexturePromises.set(path, p);
  return p;
}

function loadSideMarkerTexture(path: string): Promise<PIXI.Texture> {
  const cached = sideMarkerTextureCache.get(path);
  if (cached) return Promise.resolve(cached);
  const existing = sideMarkerTexturePromises.get(path);
  if (existing) return existing;

  const p = PIXI.Assets.load(path)
    .then((tex) => {
      sideMarkerTextureCache.set(path, tex);
      return tex;
    })
    .finally(() => {
      sideMarkerTexturePromises.delete(path);
    });
  sideMarkerTexturePromises.set(path, p);
  return p;
}

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
  showMap: boolean,
  fortifications: { type: string; q: number; r: number; orientation?: number; vertex_start?: number; vertex_end?: number }[] = [],
  vps: { q: number; r: number; value?: number; current_owner?: string | null }[] = [],
  showGrid: boolean = true,
) {
  const [width, height] = shape;

  const g = new PIXI.Graphics();
  container.sortableChildren = true;

  const terrainMap = new Map<number, string>();
  for (const h of hexes) {
    terrainMap.set(h.q * 100 + h.r, h.terrain);
  }
  const fortificationMap = new Map<number, { type: string; orientation?: number; vertex_start?: number; vertex_end?: number }>();
  for (const item of fortifications) {
    fortificationMap.set(item.q * 100 + item.r, {
      type: item.type,
      orientation: item.orientation,
      vertex_start: item.vertex_start,
      vertex_end: item.vertex_end,
    });
  }
  const vpMap = new Map<number, { value?: number; current_owner?: string | null }>();
  for (const vp of vps) {
    vpMap.set(vp.q * 100 + vp.r, { value: vp.value, current_owner: vp.current_owner });
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

      if (showGrid) {
        if (!showMap) {
          drawHex(g, px, py, HEX_SIZE, getTerrainColor(terrain), 0.6);
        } else {
          drawHex(g, px, py, HEX_SIZE);
        }
      }

      const coord = axialToLabel(q, r);
      const shortLabel = `${coord}\n${getTerrainShort(terrain)}`;
      const fort = fortificationMap.get(q * 100 + r);
      const vp = vpMap.get(q * 100 + r);
      const fortLabel = fort ? `\n${getFortificationShort(fort.type)}` : "";
      const fullLabel = `${coord}\n${getTerrainLabel(terrain)}${fortLabel}`;

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

      if (fort) {
        const fortArt = getFortificationArt(fort.type);
        const renderCfg = getFortificationRender(fort.type);
        const orientation = fort.orientation;
        const edgeStart = fort.vertex_start;
        const edgeEnd = fort.vertex_end;
        const edgeRotation = (() => {
          if (orientation != null && orientation >= 1 && orientation <= 6) {
            // 1 = North, then clockwise every 60 degrees.
            return ((orientation - 1) * Math.PI) / 3;
          }
          if (edgeStart == null || edgeEnd == null) return 0;
          // Vertex convention: 1 = North, clockwise.
          // Rotation baseline: edge 1->2.
          const a = Math.min(edgeStart, edgeEnd);
          return ((a - 1) * Math.PI) / 3;
        })();
        const edgeAnchorAngle = edgeRotation - Math.PI / 6;
        // Local edge frame so nudges remain consistent after rotation:
        // - normal: points from hex center toward fortified edge
        // - tangent: runs along the fortified edge
        const nx = Math.cos(edgeAnchorAngle);
        const ny = Math.sin(edgeAnchorAngle);
        const tx = -ny;
        const ty = nx;

        const edgeDx = nx * HEX_SIZE * renderCfg.edgeOffset;
        const edgeDy = ny * HEX_SIZE * renderCfg.edgeOffset;
        const nudgeDx = tx * HEX_SIZE * renderCfg.xNudge + nx * HEX_SIZE * renderCfg.yNudge;
        const nudgeDy = ty * HEX_SIZE * renderCfg.xNudge + ny * HEX_SIZE * renderCfg.yNudge;
        const drawX = Math.round(px + edgeDx + nudgeDx);
        const drawY = Math.round(py + edgeDy + nudgeDy);
        if (fortArt) {
          const tex = getFortTexture(fortArt);
          if (tex) {
            const sprite = new PIXI.Sprite(tex);
            sprite.anchor.set(0.5);
            sprite.x = drawX;
            sprite.y = drawY;
            sprite.width = HEX_SIZE * renderCfg.scaleX;
            sprite.height = HEX_SIZE * renderCfg.scaleY;
            sprite.alpha = 0.95;
            sprite.rotation = edgeRotation;
            sprite.zIndex = 5;
            coordsLayer.addChild(sprite);
          } else {
            let marker: PIXI.Text | null = null;
            if (showCoords) {
              marker = new PIXI.Text({
                text: getFortificationShort(fort.type),
                style: {
                  fill: "#ffe699",
                  fontSize: 10,
                  fontWeight: "bold",
                  stroke: { color: "#000000", width: 3 },
                },
                resolution: 2,
              });
              marker.anchor.set(0.5);
              marker.x = drawX;
              marker.y = Math.round(drawY + HEX_SIZE * 0.08);
              marker.zIndex = 5;
              coordsLayer.addChild(marker);
            }

            void loadFortTexture(fortArt)
              .then((loaded) => {
                if (marker && !marker.parent) return;
                const sprite = new PIXI.Sprite(loaded);
                sprite.anchor.set(0.5);
                sprite.x = drawX;
                sprite.y = drawY;
                sprite.width = HEX_SIZE * renderCfg.scaleX;
                sprite.height = HEX_SIZE * renderCfg.scaleY;
                sprite.alpha = 0.95;
                sprite.rotation = edgeRotation;
                sprite.zIndex = 5;
                coordsLayer.addChild(sprite);
                if (marker) marker.destroy();
              })
              .catch(() => {
                // Keep marker fallback when image cannot be loaded.
              });
          }
        } else {
          if (showCoords) {
            const marker = new PIXI.Text({
              text: getFortificationShort(fort.type),
              style: {
                fill: "#ffe699",
                fontSize: 10,
                fontWeight: "bold",
                stroke: { color: "#000000", width: 3 },
              },
              resolution: 2,
            });
            marker.anchor.set(0.5);
            marker.x = drawX;
            marker.y = Math.round(drawY + HEX_SIZE * 0.08);
            marker.zIndex = 5;
            coordsLayer.addChild(marker);
          }
        }
      }

      if (vp) {
        const owner = (vp.current_owner || "").toUpperCase();
        const sideDef = owner ? sides[owner] : null;
        const markerPath = sideDef?.marker as string | undefined;
        const markerX = Math.round(px + HEX_SIZE * 0.58);
        const markerY = Math.round(py - HEX_SIZE * 0.62);
        const vpValueText = String(vp.value ?? "");

        const addFallbackOwnerBadge = () => {
          if (!owner) return;
          const badge = new PIXI.Graphics();
          const fillColor = typeof sideDef?.bgColor === "number" ? sideDef.bgColor : 0x333333;
          badge.circle(markerX, markerY, HEX_SIZE * 0.27);
          badge.fill({ color: fillColor, alpha: 0.95 });
          badge.stroke({ color: 0xffffff, width: 1.5, alpha: 0.9 });
          badge.zIndex = 7;
          coordsLayer.addChild(badge);

          const ownerText = new PIXI.Text({
            text: sideDef?.short_label || owner,
            style: {
              fill: "#ffffff",
              fontSize: 7,
              fontWeight: "bold",
              stroke: { color: "#000000", width: 2 },
            },
            resolution: 2,
          });
          ownerText.anchor.set(0.5);
          ownerText.x = markerX;
          ownerText.y = markerY + 1;
          ownerText.zIndex = 8;
          coordsLayer.addChild(ownerText);
        };

        if (markerPath) {
          void loadSideMarkerTexture(markerPath)
            .then((tex) => {
              const sprite = new PIXI.Sprite(tex);
              sprite.anchor.set(0.5);
              sprite.x = markerX;
              sprite.y = markerY;
              sprite.width = HEX_SIZE * 0.52;
              sprite.height = HEX_SIZE * 0.52;
              sprite.alpha = 0.95;
              sprite.zIndex = 7;
              coordsLayer.addChild(sprite);
            })
            .catch(() => {
              addFallbackOwnerBadge();
            });
        } else {
          addFallbackOwnerBadge();
        }

        if (!markerPath || showCoords) {
          const vpText = new PIXI.Text({
            text: markerPath ? owner : "VP",
            style: {
              fill: markerPath ? "#ffffff" : "#ffe699",
              fontSize: 9,
              fontWeight: "bold",
              stroke: { color: "#000000", width: 3 },
            },
            resolution: 2,
          });
          vpText.anchor.set(0.5);
          vpText.x = markerX;
          vpText.y = markerY;
          vpText.zIndex = 8;
          coordsLayer.addChild(vpText);
        }

        if (vpValueText) {
          const valueX = Math.round(markerX + HEX_SIZE * 0.23);
          const valueY = Math.round(markerY - HEX_SIZE * 0.23);

          const valueBadge = new PIXI.Graphics();
          valueBadge.circle(valueX, valueY, HEX_SIZE * 0.18);
          valueBadge.fill({ color: 0x000000, alpha: 0.9 });
          valueBadge.stroke({ color: 0xffffff, width: 1.5, alpha: 0.95 });
          valueBadge.zIndex = 9;
          coordsLayer.addChild(valueBadge);

          const valueText = new PIXI.Text({
            text: vpValueText,
            style: {
              fill: "#ffffff",
              fontSize: 9,
              fontWeight: "bold",
              stroke: { color: "#000000", width: 2 },
            },
            resolution: 2,
          });
          valueText.anchor.set(0.5);
          valueText.x = valueX;
          valueText.y = valueY;
          valueText.zIndex = 10;
          coordsLayer.addChild(valueText);
        }
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

  if (showGrid) {
    container.addChild(g);
  }
}