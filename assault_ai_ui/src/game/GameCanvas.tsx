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
import { clearUnitActionMarkers, resolveActionMarker, setUnitActionMarker, syncUnitActionMarkers } from "./state/actionMarkers";

import { subscribeToGameState } from "./systems/gameStateSystem";
import { registerFocusUnit } from "./systems/cameraSystem";

import { HighlightLayer } from "./render/highlightLayer";
import { updateHighlights } from "./systems/highlightSystem";
import { updateLayerVisibility } from "./systems/layerVisibilitySystem";

import { createDebugVector, updateDebugVector } from "./systems/debugVectorSystem";
import { drawAttackIndicatorPixels } from "./animation/visuals";
import { soundService } from "./audio/SoundService";
import { gameController } from "./gameControllerInstance";

function isCombatOrder(order: any): boolean {
  const actionType = (order?.type || order?.kind || "").toString().toUpperCase();
  if (order?.kind === "attack") return true;
  return /RANGED|ASSAULT|ATTACK|REACTION|COMBAT|FIRE/.test(actionType);
}

function resolveAttackTargetHex(order: any, state: any): { q: number; r: number } | null {
  if (!order) return null;
  const q = order?.target_q ?? order?.q;
  const r = order?.target_r ?? order?.r;
  if (q != null && r != null) {
    return { q: Number(q), r: Number(r) };
  }
  const targetId = order?.target_id;
  if (!targetId || !Array.isArray(state?.units)) return null;
  const target = state.units.find((u: any) => u.id === targetId || u.unit_id === targetId);
  if (!target) return null;
  return { q: Number(target.q), r: Number(target.r) };
}

export default function GameCanvas({
  setGameData,
  selectedUnitId,
  setSelectedUnitId,
  availableMoves,
  setAvailableMoves,
  setAttackHint,
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
  const [orderHoverTarget, setOrderHoverTarget] = useState<any>(null);

  const lastStateRef = useRef<any>(null);
  const lastTurnRef = useRef<number | null>(null);

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
      const nextTurn = Number.isFinite(state?.turn) ? Number(state.turn) : null;
      if (
        nextTurn != null &&
        lastTurnRef.current != null &&
        nextTurn !== lastTurnRef.current
      ) {
        clearUnitActionMarkers();
      }
      if (nextTurn != null) {
        lastTurnRef.current = nextTurn;
      }

      setGameData(state);
      lastStateRef.current = state;
      // Source of truth: keep markers aligned with runtime activated_units.
      // Some intermediate payloads (e.g. websocket MAP_STATE) may not include
      // activated_units; do not treat missing field as "clear all".
      if (Array.isArray(state?.activated_units)) {
        syncUnitActionMarkers(state.activated_units);
      }

      setTimeout(() => {
        unitLayerRef.current?.sync(state);
      }, 0);
    };

  }, []);

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

      app.stage.addChild(world);
      worldRef.current = world;

      // ✅ DEBUG VECTOR EXTERNAL
      const debugVector = createDebugVector(app);
      (window as any).debugVector = debugVector;

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

        if (!closestHex) return;

        setHoverHex(prev => {
          if (!prev || prev.q !== closestHex.q || prev.r !== closestHex.r) {
            return { q: closestHex.q, r: closestHex.r };
          }
          return prev;
        });

        // ✅ DEBUG desacoplado
        updateDebugVector({
          world,
          selectedUnitId: selectedUnitRef.current,
          state: lastStateRef.current,
          closestHex,
          event,
          debug: (window as any).debugVector
        });

      });

      // ---------------------------------------------
      // CLICK MAP
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
          (window as any).onHexClick?.(closestHex.q, closestHex.r);
        }
      });

      // ---------------------------------------------
      // LAYERS
      // ---------------------------------------------
      const fxLayer = new PIXI.Container();
      app.stage.addChild(fxLayer);
      fxLayerRef.current = fxLayer;

      const background = new PIXI.Container();
      const grid = new PIXI.Container();

      world.addChild(background);
      world.addChild(grid);

      backgroundRef.current = background;
      gridRef.current = grid;

      const unitLayer = new UnitLayer(world);
      unitLayerRef.current = unitLayer;

      const highlightLayer = new HighlightLayer(world);
      highlightLayerRef.current = highlightLayer;

      // ✅ conectar con GameController
      gameController.setHighlightLayer(highlightLayer);

      // ---------------------------------------------
      // CAMERA
      // ---------------------------------------------
      setupCamera(app, world, containerRef.current!);
      registerFocusUnit(worldRef, appRef, lastStateRef);

      // ---------------------------------------------
      // UNIT CLICK
      // ---------------------------------------------
      (window as any).onUnitClick = (unit: any) => {
        if (unit?.hp != null && unit.hp <= 0) {
          return;
        }

        const data = lastStateRef.current;
        const currentSelected = selectedUnitRef.current;
        const currentMoves = availableMovesRef.current || [];

        const attackMove = currentSelected
          ? currentMoves.find((m: any) =>
              m.kind === "attack" &&
              (m.target_id === unit.id || (m.q === unit.q && m.r === unit.r))
            )
          : null;

        if (attackMove && currentSelected) {
          handleHexClick(
            attackMove.q ?? unit.q,
            attackMove.r ?? unit.r,
            currentSelected,
            currentMoves,
            unitLayerRef,
            appRef,
            fxLayerRef,
            setAvailableMoves,
            setSelectedUnitId
          );
          return;
        }

        setSelectedUnitId(unit.id);
        handleUnitClick(unit, data, setAvailableMoves, setAttackHint);
      };

      (window as any).onOrderHover = (order: any) => {
        setOrderHoverTarget(order);
      };

      (window as any).onOrderLeave = () => {
        setOrderHoverTarget(null);
      };

      (window as any).onHexClick = (q: number, r: number) => {
        const current = lastStateRef.current;
        const activeSide = current?.active_side;
        const isHumanTurn = current?.sides?.[activeSide] === "human";
        if (!isHumanTurn) return;
        handleHexClick(
          q,
          r,
          selectedUnitRef.current,
          availableMovesRef.current,
          unitLayerRef,
          appRef,
          fxLayerRef,
          setAvailableMoves,
          setSelectedUnitId
        );
      };

      (window as any).onAIAnimateOrder = async (order: any) => {
        if (!order) return;
        const unitId = order?.unit_id || order?.unit;
        const moveQ = order?.move_q ?? order?.move_to?.q ?? order?.q;
        const moveR = order?.move_r ?? order?.move_to?.r ?? order?.r;
        const actionType = String(order?.type || order?.kind || "").toUpperCase();
        const rawAction = String(order?.action || "").toUpperCase();
        const isMove = actionType === "MOVE" || order?.kind === "move";
        const isAttack = isCombatOrder(order);
        const isMoveThenFire =
          actionType === "MOVE_THEN_FIRE" ||
          rawAction.includes("MOVETHENFIRE");
        const isFireThenMove =
          actionType === "FIRE_THEN_MOVE" ||
          rawAction.includes("FIRETHENMOVE");

        // Composite animation parity with human orders.
        if (isMoveThenFire && unitId && moveQ != null && moveR != null) {
          await unitLayerRef.current?.moveUnit(unitId, moveQ, moveR);
        }

        if (isAttack && unitId && unitLayerRef.current) {
          soundService.playAttack();
          const preState = lastStateRef.current;
          const attacker = preState?.units?.find((u: any) => u.id === unitId || u.unit_id === unitId);
          const targetHex = resolveAttackTargetHex(order, preState);
          const fxLayer =
            unitLayerRef.current.container?.parent?.children.find((c: any) => c.label === "fxLayer") ||
            unitLayerRef.current.container?.parent;
          if (attacker && targetHex && fxLayer) {
            const from = axialToPixel(attacker.q, attacker.r);
            const to = axialToPixel(targetHex.q, targetHex.r);
            drawAttackIndicatorPixels(
              from.x,
              from.y + HEX_SIZE,
              to.x,
              to.y + HEX_SIZE,
              fxLayer
            );
            await new Promise((r) => setTimeout(r, 420));
          }
        }

        if (isFireThenMove && unitId && moveQ != null && moveR != null) {
          await unitLayerRef.current?.moveUnit(unitId, moveQ, moveR);
        } else if (isMove && unitId && moveQ != null && moveR != null) {
          await unitLayerRef.current?.moveUnit(unitId, moveQ, moveR);
        }
      };

      (window as any).onExecuteOrder = async (order: any) => {
        const current = lastStateRef.current;
        const activeSide = current?.active_side;
        const isHumanTurn = current?.sides?.[activeSide] === "human";
        if (!isHumanTurn) return false;
        const actionId = order?.action_id;
        const unitId = order?.unit_id || selectedUnitRef.current;
        if (!actionId || !unitId) return false;

        const actionType = (order?.type || order?.kind || "").toString().toUpperCase();
        const isAttack = isCombatOrder(order);
        const moveQ = order?.move_q ?? order?.move_to?.q;
        const moveR = order?.move_r ?? order?.move_to?.r;
        const isMoveThenFire = actionType === "MOVE_THEN_FIRE";
        const isFireThenMove = actionType === "FIRE_THEN_MOVE";
        setUnitActionMarker(unitId, resolveActionMarker(order));

        // Composite animation: move first for MOVE_THEN_FIRE.
        if (isMoveThenFire && moveQ != null && moveR != null) {
          await unitLayerRef.current?.moveUnit(unitId, moveQ, moveR);
        }

        if (isAttack && unitLayerRef.current) {
          const preState = lastStateRef.current;
          const attacker = preState?.units?.find((u: any) => u.id === unitId || u.unit_id === unitId);
          const targetHex = resolveAttackTargetHex(order, preState);
          const fxLayer =
            unitLayerRef.current.container?.parent?.children.find((c: any) => c.label === "fxLayer") ||
            unitLayerRef.current.container?.parent;
          if (attacker && targetHex && fxLayer) {
            const from = axialToPixel(attacker.q, attacker.r);
            const to = axialToPixel(targetHex.q, targetHex.r);
            drawAttackIndicatorPixels(
              from.x,
              from.y + HEX_SIZE,
              to.x,
              to.y + HEX_SIZE,
              fxLayer
            );
            await new Promise((r) => setTimeout(r, 420));
          }
        }

        setSelectedUnitId(null);
        setAvailableMoves([]);

        const stepRes = await fetch("http://127.0.0.1:8000/api/game/step", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ action_id: actionId }),
        });
        const stepData = await stepRes.json();
        const stateAfter = stepData?.state;
        if (!stateAfter || typeof stateAfter !== "object") {
          console.error("❌ Invalid step response: missing state", stepData);
          (window as any).logSystemEvent?.("system", "❌ Invalid backend step response (no state).");
          return false;
        }

        // Combat FX for attack orders.
        if (isAttack && stateAfter?.last_events && unitLayerRef?.current) {
          const combatEvent = stateAfter.last_events.find((e: any) => e.type === "ACTION_EFFECT");
          const fxLayer = unitLayerRef.current.container?.parent?.children.find(
            (c: any) => c.label === "fxLayer"
          ) || unitLayerRef.current.container?.parent;
          const attackerUnit = stateAfter.units?.find(
            (u: any) => u.id === unitId || u.unit_id === unitId
          );
          const targetId = order?.target_id;
          const defenderUnit = targetId
            ? stateAfter.units?.find((u: any) => u.id === targetId || u.unit_id === targetId)
            : null;

          if (combatEvent && fxLayer && attackerUnit && defenderUnit) {
            const { playCombatFX } = await import("./animation/combatFx");
            await playCombatFX(
              fxLayer,
              { q: attackerUnit.q, r: attackerUnit.r },
              { q: defenderUnit.q, r: defenderUnit.r },
              combatEvent.payload?.attack_dice || ["DAMAGE"],
              combatEvent.payload?.defense_dice || []
            );
          }
        }

        // Composite animation: move after fire for FIRE_THEN_MOVE.
        if (isFireThenMove && moveQ != null && moveR != null) {
          await unitLayerRef.current?.moveUnit(unitId, moveQ, moveR);
        }

        (window as any).__setGameState?.(stateAfter);
        try {
          // Keep GameController loop state in sync after human actions.
          // If controller.state lags behind, AI turn ownership checks can skip
          // backend ai-turn calls and animations after first cycle.
          gameController.updateState(stateAfter);
        } catch {
          // Ignore bridge failures; __setGameState already updated canvas state.
        }

        return true;
      };

      // ---------------------------------------------
      // GAME STATE SUB
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
      (window as any).onOrderHover = undefined;
      (window as any).onOrderLeave = undefined;
      (window as any).onExecuteOrder = undefined;
      (window as any).onAIAnimateOrder = undefined;
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
      hoverHex,
      orderHoverTarget
    );

  }, [availableMoves, selectedUnitId, hoverHex, orderHoverTarget]);

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