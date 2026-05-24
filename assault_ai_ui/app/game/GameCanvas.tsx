import { useEffect, useRef, useState } from "react";
import * as PIXI from "pixi.js";

import { drawHexGridBase } from "./renderers/hexGridRenderer";
import { setupCamera } from "./systems/cameraController";
import { drawMapPieces } from "./renderers/mapPieceRenderer";

export default function GameCanvas() {
  const containerRef = useRef<HTMLDivElement>(null);
  const appRef = useRef<PIXI.Application | null>(null);

  const [layers, setLayers] = useState({
    background: true,
    grid: true,
    units: true,
    debug: true,
  });

  const backgroundLayerRef = useRef<PIXI.Container | null>(null);
  const gridLayerRef = useRef<PIXI.Container | null>(null);
  const unitLayerRef = useRef<PIXI.Container | null>(null);
  const debugLayerRef = useRef<PIXI.Container | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // ✅ LIMPIAR DOM
    containerRef.current.innerHTML = "";

    // ✅ 🔥 CLAVE: destruir Pixi anterior
    if (appRef.current) {
      appRef.current.destroy(true, { children: true });
      appRef.current = null;
    }

    async function init() {
      const response = await fetch(
        "http://127.0.0.1:8000/api/ui/scenarios/mettete_i_piedi_terra_1_min"
      );

      const data = await response.json();
      console.log("SCENARIO:", data);

      const app = new PIXI.Application();
      appRef.current = app;

      await app.init({
        resizeTo: containerRef.current!,
        background: "#000000",
      });

      containerRef.current!.appendChild(app.canvas);

      // ✅ WORLD ÚNICO
      const world = new PIXI.Container();
      app.stage.addChild(world);

      // ✅ CAPAS (UNA SOLA INSTANCIA)
      const backgroundLayer = new PIXI.Container();
      const gridLayer = new PIXI.Container();
      const unitLayer = new PIXI.Container();
      const debugLayer = new PIXI.Container();

      // ✅ GUARDAR REFS
      backgroundLayerRef.current = backgroundLayer;
      gridLayerRef.current = gridLayer;
      unitLayerRef.current = unitLayer;
      debugLayerRef.current = debugLayer;

      // ✅ Añadir al world
      world.addChild(backgroundLayer);
      world.addChild(gridLayer);
      world.addChild(unitLayer);
      world.addChild(debugLayer);

      // ✅ DEBUG GLOBAL
      (window as any).bg = backgroundLayer;
      (window as any).grid = gridLayer;

      console.log("FINAL BG:", backgroundLayer);

      // ✅ CAMERA
      setupCamera(app, world, containerRef.current!);

      // ✅ DRAW
      if (data.map?.pieces) {
        await drawMapPieces(backgroundLayer, data.map.pieces);
      }

      drawHexGridBase(gridLayer, data.shape);

      // ✅ DEBUG POINTS
      for (const hex of data.hexes) {
        const g = new PIXI.Graphics();
        g.circle(hex.q * 40, hex.r * 40, 4).fill(0x00ff00);
        debugLayer.addChild(g);
      }
    }

    init();
  }, []);

  // ✅ TOGGLE REAL
  const toggleLayer = (key: string, value: boolean) => {
    console.log("TOGGLE:", key, value);

    if (key === "background" && backgroundLayerRef.current) {
      backgroundLayerRef.current.visible = value;
    }

    if (key === "grid" && gridLayerRef.current) {
      gridLayerRef.current.visible = value;
    }

    if (key === "units" && unitLayerRef.current) {
      unitLayerRef.current.visible = value;
    }

    if (key === "debug" && debugLayerRef.current) {
      debugLayerRef.current.visible = value;
    }

    setLayers((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <>
      {/* ✅ PANEL */}
      <div
        style={{
          position: "absolute",
          top: 10,
          left: 10,
          zIndex: 10,
          background: "#222",
          padding: "10px",
          borderRadius: 6,
          color: "white",
        }}
      >
        <b>Layers</b>

        <div>
          <label>
            <input
              type="checkbox"
              checked={layers.background}
              onChange={(e) =>
                toggleLayer("background", e.target.checked)
              }
            />
            {" "}Background
          </label>
        </div>

        <div>
          <label>
            <input
              type="checkbox"
              checked={layers.grid}
              onChange={(e) =>
                toggleLayer("grid", e.target.checked)
              }
            />
            {" "}Grid
          </label>
        </div>

        <div>
          <label>
            <input
              type="checkbox"
              checked={layers.units}
              onChange={(e) =>
                toggleLayer("units", e.target.checked)
              }
            />
            {" "}Units
          </label>
        </div>

        <div>
          <label>
            <input
              type="checkbox"
              checked={layers.debug}
              onChange={(e) =>
                toggleLayer("debug", e.target.checked)
              }
            />
            {" "}Debug
          </label>
        </div>
      </div>

      {/* ✅ CANVAS */}
      <div
        ref={containerRef}
        style={{
          width: "100%",
          height: "100%",
        }}
      />
    </>
  );
}