import { useEffect, useRef, useState } from "react";
import * as PIXI from "pixi.js";

import { gameController } from "./gameControllerInstance";
import { drawHexGridBase } from "./render/hexGridRenderer";
import { drawMapPieces } from "./render/mapPieceRenderer";
import { setupCamera } from "./systems/cameraController";
import LayerControls from "./systems/LayerControls";

export default function GameCanvas() {

  const containerRef = useRef<HTMLDivElement | null>(null);
  const appRef = useRef<PIXI.Application | null>(null);

  // ✅ PIXI refs
  const backgroundRef = useRef<PIXI.Container | null>(null);
  const gridRef = useRef<PIXI.Container | null>(null);

  const subscribedRef = useRef(false);
  const initializedRef = useRef(false);

  // ✅ UI state
  const [showMap, setShowMap] = useState(true);
  const [showGrid, setShowGrid] = useState(true);
  const [showCoords, setShowCoords] = useState(false);

  // ✅ refs para PIXI
  const showMapRef = useRef(true);
  const showGridRef = useRef(true);
  const showCoordsRef = useRef(false);

  // ✅ guardar último estado
  const lastStateRef = useRef<any>(null);

  // ---------------------------------------------
  // ✅ SYNC VISIBILITY + REDRAW
  // ---------------------------------------------
  useEffect(() => {
    showMapRef.current = showMap;
    showGridRef.current = showGrid;
    showCoordsRef.current = showCoords;

    if (!backgroundRef.current || !gridRef.current) return;

    backgroundRef.current.visible = showMap;
    gridRef.current.visible = showGrid;

    // ✅ redraw grid con coords + terrain
    const state = lastStateRef.current;
    if (!state) return;

    const data = state.raw;
    if (!data) return;

    const grid = gridRef.current;

    grid.removeChildren();

    drawHexGridBase(grid, data.shape, showCoordsRef.current, data.hexes,showMap);

  }, [showMap, showGrid, showCoords]);

  // ---------------------------------------------
  // ✅ INIT PIXI
  // ---------------------------------------------
  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;

    if (!containerRef.current) return;

    const app = new PIXI.Application();

    app.init({
      resizeTo: containerRef.current,
      background: "#000",
    }).then(() => {

      if (!containerRef.current) return;

      containerRef.current.appendChild(app.canvas);
      appRef.current = app;

      const world = new PIXI.Container();
      app.stage.addChild(world);

      const background = new PIXI.Container();
      const grid = new PIXI.Container();

      world.addChild(background);
      world.addChild(grid);

      backgroundRef.current = background;
      gridRef.current = grid;

      background.visible = showMapRef.current;
      grid.visible = showGridRef.current;

      setupCamera(app, world, containerRef.current);

      if (!subscribedRef.current) {
        subscribedRef.current = true;

        gameController.subscribe((state) => {
          lastStateRef.current = state;

          const data = state.raw;
          if (!data) return;

          background.visible = showMapRef.current;
          grid.visible = showGridRef.current;

          background.removeChildren();
          grid.removeChildren();

          if (data.map?.pieces) {
            drawMapPieces(background, data.map.pieces);
          }

          drawHexGridBase(grid, data.shape, showCoordsRef.current, data.hexes,showMap);
        });
      }

    });

    return () => {
      appRef.current?.destroy(true);
      appRef.current = null;
    };

  }, []);

  // ---------------------------------------------
  // ✅ RENDER
  // ---------------------------------------------
  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        position: "relative",
      }}
    >
      <div
        ref={containerRef}
        style={{
          width: "100%",
          height: "100%",
        }}
      />

      <LayerControls
        showMap={showMap}
        showGrid={showGrid}
        showCoords={showCoords}
        onToggleMap={setShowMap}
        onToggleGrid={setShowGrid}
        onToggleCoords={setShowCoords}
      />
    </div>
  );
}