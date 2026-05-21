import { useEffect, useRef } from "react";
import * as PIXI from "pixi.js";
import { drawHexGridBase } from "./renderers/hexGridRenderer";
import { setupCamera } from "./systems/cameraController";
import { drawMapPieces } from "./renderers/mapPieceRenderer";

export default function GameCanvas() {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    async function init() {
      // ---------------------------------
      // FETCH SCENARIO
      // ---------------------------------
      const response = await fetch(
        "http://127.0.0.1:8000/api/ui/scenarios/mettete_i_piedi_terra_1_min"
      );

      const data = await response.json();
      console.log("SCENARIO:", data);

      if (!containerRef.current) return;

      // ---------------------------------
      // PIXI APP (v8)
      // ---------------------------------
      const app = new PIXI.Application();

      await app.init({
        resizeTo: containerRef.current,
        background: "#000000",
      });

      containerRef.current.appendChild(app.canvas);

      // ---------------------------------
      // LAYERS
      // ---------------------------------
      const mapLayer = new PIXI.Container();
      const unitLayer = new PIXI.Container();
      const effectLayer = new PIXI.Container();
      const world = new PIXI.Container();
      const backgroundLayer = new PIXI.Container();

      app.stage.addChild(world);

      world.addChild(backgroundLayer)
      world.addChild(mapLayer);
      world.addChild(unitLayer);
      world.addChild(effectLayer);

      setupCamera(app, world, containerRef.current);

      await drawMapPieces(backgroundLayer, data.map.pieces);-
      drawHexGridBase(mapLayer, data.shape);


      // ---------------------------------
      // DEBUG UNITS
      // ---------------------------------
      for (const hex of data.hexes) {
        const g = new PIXI.Graphics();

        g.circle(hex.q * 40, hex.r * 40, 4).fill(0x00ff00);

        mapLayer.addChild(g);
      }
    }

    init();
  }, []);

  return (
    <div
      ref={containerRef}
      style={{
        width: "100%",
        height: "100%",
      }}
    />
  );
}