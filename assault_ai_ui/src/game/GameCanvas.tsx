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

    const state = lastStateRef.current;
    if (!state) return;

    const data = state.raw;
    if (!data) return;

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

      if (!containerRef.current) return;

      containerRef.current.appendChild(app.canvas);
      appRef.current = app;

      requestAnimationFrame(() => {
        if (!containerRef.current) return;

        const w = containerRef.current.clientWidth;
        const h = containerRef.current.clientHeight;

        app.renderer.resize(w, h);
      });

      // ✅ WORLD
      const world = new PIXI.Container();
      app.stage.addChild(world);
      worldRef.current = world;

      const background = new PIXI.Container();
      const grid = new PIXI.Container();

      world.addChild(background);
      world.addChild(grid);

      // ✅ UNITS
      const unitLayer = new UnitLayer(world);
      unitLayerRef.current = unitLayer;

      backgroundRef.current = background;
      gridRef.current = grid;

      background.visible = showMapRef.current;
      grid.visible = showGridRef.current;

      setupCamera(app, world, containerRef.current);

      // ✅ 🔥 FOCUS CAMERA DESDE PANEL
      (window as any).focusUnit = (unitId: string) => {
        const state = lastStateRef.current;
        if (!state) return;

        const units = state.raw?.units;
        if (!units) return;

        const unit = units.find((u: any) => u.id === unitId);
        if (!unit) return;

        const { x, y } = axialToPixel(unit.q, unit.r);

        const world = worldRef.current;
        const app = appRef.current;

        if (!world || !app) return;

        // ✅ centrar cámara
        world.pivot.set(x, y + HEX_SIZE);
        world.position.set(
          app.renderer.width / 2,
          app.renderer.height / 2
        );
      };

      // ---------------------------------------------
      // SUBSCRIBE
      // ---------------------------------------------
      if (!subscribedRef.current) {
        subscribedRef.current = true;

        gameController.subscribe((state) => {
          lastStateRef.current = state;

          const data = state.raw;
          if (!data) return;

          setGameData({
            units: data.units || []
          });

          background.visible = showMapRef.current;
          grid.visible = showGridRef.current;

          background.removeChildren();
          grid.removeChildren();

          // ✅ MAP
          if (data.map?.pieces) {
            drawMapPieces(background, data.map.pieces);
          }

          // ✅ GRID
          if (data.shape && data.hexes) {
            drawHexGridBase(
              grid,
              data.shape,
              showCoordsRef.current,
              data.hexes,
              showMapRef.current
            );
          }

          // ✅ UNITS
          if (unitLayerRef.current && data.units) {
            unitLayerRef.current.sync(data.units);
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
      position: "relative",
    }}>

      {/* MAP */}
      <div style={{
        flex: 1,
        position: "relative",
      }}>
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

      {/* PANEL */}
      <UnitStatePanel units={gameData?.units || []} />

    </div>
  );
}