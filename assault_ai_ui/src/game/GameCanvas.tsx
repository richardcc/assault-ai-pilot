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
  const initializedRef = useRef(false); // 🔥 CLAVE

  // ✅ UI state
  const [showMap, setShowMap] = useState(true);
  const [showGrid, setShowGrid] = useState(true);

  // ✅ refs para evitar stale closure
  const showMapRef = useRef(true);
  const showGridRef = useRef(true);

  useEffect(() => {
    showMapRef.current = showMap;
    showGridRef.current = showGrid;

    // ✅ proteger null
    if (!backgroundRef.current || !gridRef.current) return;

    backgroundRef.current.visible = showMap;
    gridRef.current.visible = showGrid;

  }, [showMap, showGrid]);

  useEffect(() => {
    if (initializedRef.current) return; // 🔥 evita doble init (React StrictMode)
    initializedRef.current = true;

    if (!containerRef.current) return;

    const app = new PIXI.Application();

    app.init({
      resizeTo: containerRef.current,
      background: "#000",
    }).then(() => {

      if (!containerRef.current) return; // 🔥 evita null

      containerRef.current.appendChild(app.canvas);
      appRef.current = app;

      // WORLD
      const world = new PIXI.Container();
      app.stage.addChild(world);

      // LAYERS
      const background = new PIXI.Container();
      const grid = new PIXI.Container();

      world.addChild(background);
      world.addChild(grid);

      backgroundRef.current = background;
      gridRef.current = grid;

      // ✅ VISIBILITY INICIAL
      background.visible = showMapRef.current;
      grid.visible = showGridRef.current;

      // CAMERA
      setupCamera(app, world, containerRef.current);

      // SUBSCRIBE
      if (!subscribedRef.current) {
        subscribedRef.current = true;

        gameController.subscribe((state) => {
          const data = state.raw;
          if (!data) return;

          // ✅ VISIBILITY SIEMPRE
          background.visible = showMapRef.current;
          grid.visible = showGridRef.current;

          background.removeChildren();
          grid.removeChildren();

          if (data.map?.pieces) {
            drawMapPieces(background, data.map.pieces);
          }

          drawHexGridBase(grid, data.shape);
        });
      }

    });

    return () => {
      appRef.current?.destroy(true);
      appRef.current = null;
    };

  }, []);

  return (
    <>
      <div
        ref={containerRef}
        style={{
          width: "100%",
          height: "100%",
          position: "relative",
        }}
      />

      <LayerControls
        showMap={showMap}
        showGrid={showGrid}
        onToggleMap={setShowMap}
        onToggleGrid={setShowGrid}
      />
    </>
  );
}