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

  // ✅ LAYER REFS
  const backgroundRef = useRef<PIXI.Container | null>(null);
  const gridRef = useRef<PIXI.Container | null>(null);

  // ✅ FIX: hook en lugar correcto
  const subscribedRef = useRef(false);

  // ✅ STATE UI
  const [showMap, setShowMap] = useState(true);
  const [showGrid, setShowGrid] = useState(true);

  useEffect(() => {
    if (!containerRef.current) return;

    const app = new PIXI.Application();

    app.init({
      resizeTo: containerRef.current!,
      background: "#000",
    }).then(() => {

      containerRef.current!.appendChild(app.canvas);
      appRef.current = app;

      // ✅ WORLD
      const world = new PIXI.Container();
      app.stage.addChild(world);

      // ✅ LAYERS
      const background = new PIXI.Container();
      const grid = new PIXI.Container();

      world.addChild(background);
      world.addChild(grid);

      backgroundRef.current = background;
      gridRef.current = grid;

      // ✅ CAMERA
      setupCamera(app, world, containerRef.current!);

      // ✅ SUBSCRIBE (protegido)
      if (!subscribedRef.current) {
        subscribedRef.current = true;

        gameController.subscribe((state) => {
          const data = state.raw;
          if (!data) return;

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
    };

  }, []);

  // ✅ VISIBILITY SYNC
  useEffect(() => {
    if (backgroundRef.current) {
      backgroundRef.current.visible = showMap;
    }

    if (gridRef.current) {
      gridRef.current.visible = showGrid;
    }
  }, [showMap, showGrid]);

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
