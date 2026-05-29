import { useEffect, useRef, useState } from "react";
import * as PIXI from "pixi.js";

import {
  axialToPixel,
  HEX_SIZE
} from "./render/hexGridRenderer";

import { setupCamera } from "./systems/cameraController";

import LayerControls from "./systems/LayerControls";
import { UnitLayer } from "./render/unitLayer";

import { handleUnitClick } from "./systems/unitInteractionSystem";
import { handleHexClick } from "./systems/hexInteractionSystem";

import { subscribeToGameState } from "./systems/gameStateSystem";
import { registerFocusUnit } from "./systems/cameraSystem";

import { HighlightLayer } from "./render/highlightLayer";
import { updateHighlights } from "./systems/highlightSystem";
import { updateLayerVisibility } from "./systems/layerVisibilitySystem";

export default function GameCanvas({
  setGameData,
  selectedUnitId,
  setSelectedUnitId,
  availableMoves,
  setAvailableMoves,
}: any) {

  const containerRef = useRef<HTMLDivElement | null>(null);
  const appRef = useRef<PIXI.Application | null>(null);

  const worldRef = useRef<PIXI.Container | null>(null);
  const backgroundRef = useRef<PIXI.Container | null>(null);
  const gridRef = useRef<PIXI.Container | null>(null);
  const unitLayerRef = useRef<UnitLayer | null>(null);
  const highlightLayerRef = useRef<HighlightLayer | null>(null);

  const subscribedRef = useRef(false);
  const initializedRef = useRef(false);

  const [showMap, setShowMap] = useState(true);
  const [showGrid, setShowGrid] = useState(true);
  const [showCoords, setShowCoords] = useState(false);

  const showMapRef = useRef(true);
  const showGridRef = useRef(true);
  const showCoordsRef = useRef(false);

  const [hoverHex, setHoverHex] = useState<{ q: number, r: number } | null>(null);

  const lastStateRef = useRef<any>(null);

  // 💣 FIX CLAVE: refs para evitar stale state
  const selectedUnitRef = useRef<string | null>(null);
  const availableMovesRef = useRef<any[]>([]);
  const fxLayerRef = useRef<PIXI.Container | null>(null);
  
  useEffect(() => {
    selectedUnitRef.current = selectedUnitId;
  }, [selectedUnitId]);

  useEffect(() => {
    availableMovesRef.current = availableMoves;
  }, [availableMoves]);

  useEffect(() => {

    (window as any).__setGameState = (state: any) => {
      console.log("💣 applying full state", state);

      setGameData(state);
      lastStateRef.current = state;

      // 💣 FIX: asegurar que Pixi sync se ejecuta en el siguiente tick
      setTimeout(() => {
        unitLayerRef.current?.sync(state);
      }, 0);
    };

  }, [])

  

  // ---------------------------------------------
  // VISIBILITY
  // ---------------------------------------------
  useEffect(() => {

    showMapRef.current = showMap;
    showGridRef.current = showGrid;
    showCoordsRef.current = showCoords;

    updateLayerVisibility(
      backgroundRef.current,
      gridRef.current,
      lastStateRef,
      showMap,
      showGrid,
      showCoords
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
      world.eventMode = "static";
      world.hitArea = app.screen;

      // ---------------------------------------------
      // HOVER
      // ---------------------------------------------
      world.on("pointermove", (event: any) => {

        const pos = world.toLocal(event.global);
        const data = lastStateRef.current;

        if (!data?.hexes) return;

        let closestHex: any = null;
        let minDist = Infinity;

        for (const hex of data.hexes) {
          const { x, y } = axialToPixel(hex.q, hex.r);

          const dx = pos.x - x;
          const dy = pos.y - (y + HEX_SIZE);
          const dist = dx * dx + dy * dy;

          if (dist < minDist) {
            minDist = dist;
            closestHex = hex;
          }
        }

        if (closestHex) {
          setHoverHex(prev => {
            if (!prev || prev.q !== closestHex.q || prev.r !== closestHex.r) {
              return { q: closestHex.q, r: closestHex.r };
            }
            return prev;
          });
        }

      });

      // ---------------------------------------------
      // 💣 CLICK MAP
      // ---------------------------------------------
      world.on("pointerdown", (event: any) => {

        const pos = world.toLocal(event.global);
        const data = lastStateRef.current;

        if (!data?.hexes) return;

        let closestHex: any = null;
        let minDist = Infinity;

        for (const hex of data.hexes) {
          const { x, y } = axialToPixel(hex.q, hex.r);

          const dx = pos.x - x;
          const dy = pos.y - (y + HEX_SIZE);
          const dist = dx * dx + dy * dy;

          if (dist < minDist) {
            minDist = dist;
            closestHex = hex;
          }
        }

        if (closestHex) {
          console.log("🖱️ CLICK DETECTED", closestHex.q, closestHex.r);

          (window as any).onHexClick?.(
            closestHex.q,
            closestHex.r
          );
        }
      });

      app.stage.addChild(world);
      worldRef.current = world;

      // 💣 FX LAYER (NUEVO)
      const fxLayer = new PIXI.Container();
      fxLayer.label = "fxLayer";

      // MUY IMPORTANTE → sobre el world
      app.stage.addChild(fxLayer);

      fxLayerRef.current = fxLayer;

      const background = new PIXI.Container();
      const grid = new PIXI.Container();

      world.addChild(background);
      world.addChild(grid);

      const unitLayer = new UnitLayer(world);
      unitLayerRef.current = unitLayer;

      const highlightLayer = new HighlightLayer(world);
      highlightLayerRef.current = highlightLayer;

      backgroundRef.current = background;
      gridRef.current = grid;

      setupCamera(app, world, containerRef.current!);
      registerFocusUnit(worldRef, appRef, lastStateRef);

      // ---------------------------------------------
      // UNIT CLICK
      // ---------------------------------------------
      (window as any).onUnitClick = (unit: any) => {
        const data = lastStateRef.current;

        setSelectedUnitId(unit.id);

        handleUnitClick(
          unit,
          data,
          setAvailableMoves
        );
      };

      // ---------------------------------------------
      // 💣 HEX CLICK (FIXED con refs)
      // ---------------------------------------------
      (window as any).onHexClick = (q: number, r: number) => {
        handleHexClick(
          q,
          r,
          selectedUnitRef.current,
          availableMovesRef.current,
          unitLayerRef,
          appRef,
          fxLayerRef, // 💣 AÑADIDO
          setAvailableMoves,
          setSelectedUnitId
        );
      };

      // ---------------------------------------------
      // GAME STATE
      // ---------------------------------------------
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

      (window as any).onUnitClick = undefined;
      (window as any).onHexClick = undefined;
    };

  }, []);

  // ---------------------------------------------
  // HIGHLIGHTS
  // ---------------------------------------------
  useEffect(() => {

    updateHighlights(
      highlightLayerRef.current,
      lastStateRef.current,
      selectedUnitId,
      availableMoves,
      hoverHex
    );

  }, [availableMoves, selectedUnitId, hoverHex]);

  return (
    <div style={{ flex: 1, width: "100%", height: "100%", minHeight: 0, position: "relative", display: "flex", flexDirection: "column" }}>
      <div ref={containerRef} style={{ flex: 1, width: "100%", height: "100%" }} />

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