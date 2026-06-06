// File: systems/layerVisibilitySystem.ts

import { drawHexGridBase } from "../render/hexGridRenderer";

export function updateLayerVisibility(
  background: any,
  grid: any,
  lastStateRef: any,
  showMap: boolean,
  showGrid: boolean,
  showCoords: boolean
) {

  if (!background || !grid) return;

  background.visible = showMap;
  grid.visible = showGrid || showMap;

  const data = lastStateRef.current;
  if (!data) return;

  grid.removeChildren();

  drawHexGridBase(
    grid,
    data.shape,
    showCoords,
    data.hexes,
    showMap,
    data.map?.fortifications ?? [],
    showGrid
  );
}
