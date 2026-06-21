import { axialToPixel, HEX_SIZE, formatCoords } from "../render/hexGridRenderer";
import { resolveActionMarker, setUnitActionMarker } from "../state/actionMarkers";
import { drawAttackIndicatorPixels } from "../animation/visuals";
import { gameController } from "../gameControllerInstance";

export async function handleHexClick(
  q: number,
  r: number,
  selectedUnitId: string | null,
  availableMoves: any[],
  unitLayerRef: any,
  _appRef: any,
  _fxLayerRef: any,
  setAvailableMoves: (moves: any[]) => void,
  setSelectedUnitId: (id: string | null) => void
) {
  if (!selectedUnitId) return;

  const move = availableMoves.find(
    (m: any) => m.q === q && m.r === r
  );

  if (!move) {
    console.log("❌ no move found for hex", q, r);
    return;
  }

  const actionId = move.action_id;
  setUnitActionMarker(selectedUnitId, resolveActionMarker(move));

  // Block double-dispatch while animating
  if (unitLayerRef.current?.container?.children.find(
    (c: any) => c.__unitId === selectedUnitId
  )?.__isMoving) {
    console.warn("⛔ MOVE BLOCKED: already moving", selectedUnitId);
    return;
  }

  console.log("🎬 animating move", { id: selectedUnitId, to: { q, r } });

  // 1. If it's a move, animate the unit visually first
  const isAttack = move.kind === "attack";
  if (!isAttack) {
    await unitLayerRef.current?.moveUnit(selectedUnitId, q, r);
  } else {
    const attackerSprite = unitLayerRef.current?.container?.children?.find(
      (c: any) => c.__unitId === selectedUnitId && c.__type === "unit"
    );
    const fxLayer =
      _fxLayerRef?.current ||
      unitLayerRef.current?.container?.parent?.children?.find((c: any) => c.label === "fxLayer") ||
      unitLayerRef.current?.container?.parent;
    if (attackerSprite && fxLayer) {
      const to = axialToPixel(q, r);
      drawAttackIndicatorPixels(
        attackerSprite.x,
        attackerSprite.y,
        to.x,
        to.y + HEX_SIZE,
        fxLayer
      );
      await new Promise((r) => setTimeout(r, 420));
    }
  }

  console.log("✅ preparation complete, posting to backend");

  // 2. Clear selection immediately so the UI feels responsive
  setSelectedUnitId(null);
  setAvailableMoves([]);

  // 3. POST human step to backend
  const stepRes = await fetch("http://127.0.0.1:8000/api/game/step", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action_id: actionId }),
  });
  const stepData = await stepRes.json();
  const stateAfterHuman = stepData.state;
  if (!stateAfterHuman || typeof stateAfterHuman !== "object") {
    console.error("❌ Invalid step response: missing state", stepData);
    (window as any).logSystemEvent?.("system", "❌ Invalid backend step response (no state).");
    return;
  }

  // Log human action result
  if (isAttack) {
    const targetUnit = stateAfterHuman?.units?.find((u: any) => u.id === move.target_id);
    (window as any).logSystemEvent?.("combat", `👤 Human Order: Combat attack on ${move.target_id} at hex ${formatCoords(q, r)}`);
  } else {
    (window as any).logSystemEvent?.("move", `👤 Human Order: Move ${selectedUnitId} to hex ${formatCoords(q, r)}`);
  }

  // Trigger Combat FX if there are combat events in the human's step
  if (isAttack && stateAfterHuman?.last_events && unitLayerRef?.current) {
    const combatEvent = stateAfterHuman.last_events.find((e: any) => e.type === "ACTION_EFFECT");
    const fxLayer = unitLayerRef.current.container?.parent?.children.find(
      (c: any) => c.label === "fxLayer"
    ) || unitLayerRef.current.container?.parent;

    const attackerUnit = stateAfterHuman.units.find((u: any) => u.id === selectedUnitId);
    const defenderUnit = stateAfterHuman.units.find((u: any) => u.id === move.target_id);

    if (combatEvent && fxLayer && attackerUnit && defenderUnit) {
      const { playCombatFX } = await import("../animation/combatFx");
      await playCombatFX(
        fxLayer,
        { q: attackerUnit.q, r: attackerUnit.r },
        { q: defenderUnit.q, r: defenderUnit.r },
        combatEvent.payload?.attack_dice || ["DAMAGE"],
        combatEvent.payload?.defense_dice || []
      );
    }
  }

  // 4. Update the visual state
  (window as any).__setGameState?.(stateAfterHuman);
  try {
    // Keep authoritative controller state aligned for loop ownership checks.
    gameController.updateState(stateAfterHuman);
  } catch {
    // ignore bridge failures
  }

  // Log action completion with outcome
  if (!isAttack) {
    (window as any).logSystemEvent?.("move", `✅ Movement complete: Unit at hex ${formatCoords(q, r)}`);
  } else {
    const defenderAfter = stateAfterHuman?.units?.find((u: any) => u.id === move.target_id);
    const defenderDead = defenderAfter && defenderAfter.hp != null && defenderAfter.hp <= 0;
    const resultMsg = defenderDead ? "DESTROYED" : "Wounded";
    (window as any).logSystemEvent?.("combat", `✅ Combat complete: Target ${resultMsg}`);
  }

  // 5. AI execution is handled by GameController backend loop only.
}
