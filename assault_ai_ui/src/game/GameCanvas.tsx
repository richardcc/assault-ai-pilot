// File: GameCanvas.tsx

import { useEffect, useRef, useState } from "react";
import * as PIXI from "pixi.js";

// ❌ YA NO SE USA DIRECTAMENTE
// import { gameController } from "./gameControllerInstance";
// import { drawMapPieces } from "./render/mapPieceRenderer";

import { drawHexGridBase } from "./render/hexGridRenderer";
import { setupCamera } from "./systems/cameraController";

import LayerControls from "./systems/LayerControls";
import { UnitStatePanel } from "./ui/UnitStatePanel";
import { UnitLayer } from "./render/unitLayer";

import { handleUnitClick } from "./systems/unitInteractionSystem";
import { subscribeToGameState } from "./systems/gameStateSystem";
import { registerFocusUnit } from "./systems/cameraSystem";

export default function GameCanvas() {

  const containerRef = useRef<HTMLDivElement | null>(null);
  const appRef = useRef<PIXI.Application | null>(null);

  const worldRef = useRef<PIXI.Container | null>(null);

  const backgroundRef = useRef<PIXI.Container | null>(null);
  const gridRef = useRef<PIXI.Container | null>(null);
  const unitLayerRef = useRef<UnitLayer | null>(null);

  const subscribedRef = useRef(false);
  const initializedRef = useRef(false);

  const [showMap, setShowMap] = useState(true);
  const [showGrid, setShowGrid] = useState(true);
  const [showCoords, setShowCoords] = useState(false);

  const showMapRef = useRef(true);
  const showGridRef = useRef(true);
  const showCoordsRef = useRef(false);

  const [gameData, setGameData] = useState<any>(null);
  const [availableMoves, setAvailableMoves] = useState<any[]>([]);
  const lastStateRef = useRef<any>(null);

  // ---------------------------------------------
  // SYNC VISIBILITY (sin cambios)
  // ---------------------------------------------
  useEffect(() => {
    showMapRef.current = showMap;
    showGridRef.current = showGrid;
    showCoordsRef.current = showCoords;

    if (!backgroundRef.current || !gridRef.current) return;

    backgroundRef.current.visible = showMap;
    gridRef.current.visible = showGrid;

    const data = lastStateRef.current;
    if (!data) return;

    const grid = gridRef.current;
    grid.removeChildren();

    drawHexGridBase(
      grid,
      data.shape,
      showCoords,
      data.hexes,
      showMap
    );

  }, [showMap, showGrid, showCoords]);

  // ---------------------------------------------
  // INIT PIXI
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

      containerRef.current?.appendChild(app.canvas);
      appRef.current = app;

      const world = new PIXI.Container();
      app.stage.addChild(world);
      worldRef.current = world;

      const background = new PIXI.Container();
      const grid = new PIXI.Container();

      world.addChild(background);
      world.addChild(grid);

      const unitLayer = new UnitLayer(world);
      unitLayerRef.current = unitLayer;

      backgroundRef.current = background;
      gridRef.current = grid;

      setupCamera(app, world, containerRef.current!);

      // ✅ FIX 1: CAMERA SYSTEM
      registerFocusUnit(worldRef, appRef, lastStateRef);

      // ✅ FIX 2: INPUT SYSTEM (fuera del subscribe)
      (window as any).onUnitClick = (unit: any) => {
        const data = lastStateRef.current;

        handleUnitClick(
          unit,
          data,
          setAvailableMoves
        );
      };

      // ✅ FIX 3: SUBSCRIBE (externalizado)
      if (!subscribedRef.current) {
        subscribedRef.current = true;

        subscribeToGameState({
          setGameData,
          lastStateRef,
          background,
          grid,
          unitLayerRef,
          showMapRef,
          showGridRef,
          showCoordsRef,
        });
      }

    });

    return () => {
      appRef.current?.destroy(true);
      appRef.current = null;
    };

  }, []);

  // ---------------------------------------------
  // RENDER (sin cambios)
  // ---------------------------------------------
  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      width: "100%",
      height: "100%",
    }}>

      <div style={{
        background: "#1a1a1a",
        color: "#eee",
        padding: "8px 12px",
        display: "flex",
        gap: "20px",
      }}>
        <div>{gameData?.scenario_name ?? gameData?.id ?? "Scenario"}</div>

        <div>
          Turn: {gameData?.turn != null ? gameData.turn : "-"}
        </div>

        <div style={{
          color: gameData?.sides?.[gameData?.active_side] === "human"
            ? "lime"
            : "orange"
        }}>
          Active: {gameData?.active_side ?? "-"} (
          {gameData?.sides?.[gameData?.active_side] ?? "-"}
          )
        </div>
      </div>

      <div style={{ flex: 1, position: "relative" }}>
        <div
          ref={containerRef}
          style={{ width: "100%", height: "100%" }}
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

      <UnitStatePanel
        units={gameData?.units || []}
        activeSide={gameData?.active_side}
        activatedUnits={gameData?.activated_units || []}
      />

    </div>
  );
}