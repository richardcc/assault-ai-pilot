import { axialToPixel, HEX_SIZE, formatCoords } from "../render/hexGridRenderer";
import { runAiTurns } from "./aiTurnRunner";
import { resolveActionMarker, setUnitActionMarker } from "../state/actionMarkers";

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

  // Log action completion with outcome
  if (!isAttack) {
    (window as any).logSystemEvent?.("move", `✅ Movement complete: Unit at hex ${formatCoords(q, r)}`);
  } else {
    const defenderAfter = stateAfterHuman?.units?.find((u: any) => u.id === move.target_id);
    const defenderDead = defenderAfter && defenderAfter.hp != null && defenderAfter.hp <= 0;
    const resultMsg = defenderDead ? "DESTROYED" : "Wounded";
    (window as any).logSystemEvent?.("combat", `✅ Combat complete: Target ${resultMsg}`);
  }

  // 5. If the next active side belongs to AI — run all AI actions automatically
  const sides = stateAfterHuman?.sides ?? {};
  const activeSide = stateAfterHuman?.active_side;

  if (activeSide && sides[activeSide] === "ai") {
    console.log(`🤖 AI turn starts (side: ${activeSide})`);

    await runAiTurns(unitLayerRef);

    console.log("🤖 AI turn complete — human can move");
  }
}
