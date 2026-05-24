import { useEffect, useRef, useState } from "react";
import * as PIXI from "pixi.js";

import { gameController } from "./gameControllerInstance";
import { drawHexGridBase, axialToPixel, HEX_SIZE } from "./render/hexGridRenderer";
import { drawMapPieces } from "./render/mapPieceRenderer";
import { setupCamera } from "./systems/cameraController";
import LayerControls from "./systems/LayerControls";
import { UnitStatePanel } from "./ui/UnitStatePanel";
import { UnitLayer } from "./render/unitLayer";

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
  const lastStateRef = useRef<any>(null);

  // ---------------------------------------------
  // SYNC VISIBILITY
  // ---------------------------------------------
  useEffect(() => {
    showMapRef.current = showMap;
    showGridRef.current = showGrid;
    showCoordsRef.current = showCoords;

    if (!backgroundRef.current || !gridRef.current) return;

    backgroundRef.current.visible = showMapRef.current;
    gridRef.current.visible = showGridRef.current;

    const data = lastStateRef.current;
    if (!data?.hexes || !data?.shape) return;

    const grid = gridRef.current;
    grid.removeChildren();

    drawHexGridBase(
      grid,
      data.shape,
      showCoordsRef.current,
      data.hexes,
      showMapRef.current
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

      // ✅ FOCUS CAMERA
      (window as any).focusUnit = (unitId: string) => {
        const data = lastStateRef.current;
        if (!data?.units) return;

        const unit = data.units.find((u: any) => u.id === unitId);
        if (!unit) return;

        const { x, y } = axialToPixel(unit.q, unit.r);

        const world = worldRef.current;
        const app = appRef.current;
        if (!world || !app) return;

        world.pivot.set(x, y + HEX_SIZE);
        world.position.set(
          app.renderer.width / 2,
          app.renderer.height / 2
        );
      };

      // ---------------------------------------------
      // SUBSCRIBE (solo una vez)
      // ---------------------------------------------
      if (!subscribedRef.current) {
        subscribedRef.current = true;

        gameController.subscribe((state) => {

          const data = state;

          console.log("RECEIVED STATE FULL:", JSON.stringify(data, null, 2));

          // ✅ 1. SIEMPRE actualizar UI (Turn / Active)
          if (data) {
            setGameData(prev => ({
              ...prev,
              ...data,

              // ✅ 🔥 CLAVE: no perder piezas si WS viene vacío
              map: data.map?.pieces?.length
                ? data.map
                : prev?.map
            }));
          }

          // ✅ 2. solo render si hay mapa válido
          if (!data?.hexes || !data?.shape) return;

          lastStateRef.current = data;

          background.visible = showMapRef.current;
          grid.visible = showGridRef.current;

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
            showCoordsRef.current,
            data.hexes,
            showMapRef.current
          );

          // ✅ UNITS
          if (unitLayerRef.current) {
            unitLayerRef.current.sync(data.units || []);
          }
        });
      }

    });

    return () => {
      appRef.current?.destroy(true);
      appRef.current = null;
    };

  }, []);

  // ---------------------------------------------
  // RENDER
  // ---------------------------------------------
  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      width: "100%",
      height: "100%",
    }}>

      {/* HEADER */}
      <div style={{
        background: "#1a1a1a",
        color: "#eee",
        padding: "8px 12px",
        display: "flex",
        gap: "20px",
      }}>
        <div>{gameData?.scenario_name ?? gameData?.id ?? "Scenario"}</div>

        {/* ✅ FIX turno robusto */}
        <div>
          Turn: {gameData?.turn != null ? gameData.turn : "-"}
        </div>

        {/* ✅ FIX active robusto */}
        <div>
          Active: {gameData?.active_side ?? "-"}
        </div>
      </div>

      {/* MAP */}
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

      {/* PANEL */}
      <UnitStatePanel units={gameData?.units || []} />

    </div>
  );
}
