// File: C:\repos\python\assault\assault_ai_ui\src\game\systems\gameStateSystem.ts

import { gameController } from "../gameControllerInstance";
import { drawMapPieces } from "../render/mapPieceRenderer";
import { drawHexGridBase } from "../render/hexGridRenderer";

export function subscribeToGameState({
  setGameData,
  lastStateRef,
  background,
  grid,
  unitLayerRef,
  showMapRef,
  showGridRef,
  showCoordsRef,
  onStateRendered,
}: any) {

  gameController.subscribe((state) => {

    const data = state;

    console.log("RECEIVED STATE FULL:", JSON.stringify(data, null, 2));

    // ✅ UI update
    if (data) {
      setGameData(prev => ({
        ...prev,
        ...data,
        map: data.map?.pieces?.length
          ? data.map
          : prev?.map
      }));
    }

    if (!data?.hexes || !data?.shape) return;

    lastStateRef.current = data;

    const showCoordsNow = showCoordsRef.current;
    const showMapNow = showMapRef.current;

    background.visible = showMapRef.current;
    grid.visible = showGridRef.current || showMapRef.current;

    background.removeChildren();
    grid.removeChildren();

    // ✅ MAP
    const pieces = data.map?.pieces ?? lastStateRef.current?.map?.pieces ?? [];

    if (pieces.length) {
      drawMapPieces(background, pieces);
    }

    // ✅ GRID
    drawHexGridBase(
      grid,
      data.shape,
      showCoordsNow,
      data.hexes,
      showMapNow,
      data.map?.fortifications ?? [],
      data.map?.vps ?? [],
      showGridRef.current
    );

    // ✅ UNITS
    if (unitLayerRef.current) {
      unitLayerRef.current.sync(data);
    }

    if (typeof onStateRendered === "function") {
      onStateRendered(data);
    }

  });
}