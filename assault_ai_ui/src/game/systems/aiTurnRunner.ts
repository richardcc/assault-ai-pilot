import { formatCoords } from "../render/hexGridRenderer";

/**
 * aiTurnRunner.ts
 *
 * After a human action completes, this runner automatically executes
 * all pending AI actions until the active side is human again.
 * It queries the backend for valid actions, picks the best one, and steps.
 */

import { gameController } from "../gameControllerInstance";
import { axialToPixel, HEX_SIZE } from "../render/hexGridRenderer";
import { logCombatEvents } from "./combatLog";
import { resolveActionMarker, setUnitActionMarker } from "../state/actionMarkers";

const BACKEND = "http://127.0.0.1:8000";
const AI_DELAY_MS = 800; // pause between AI actions so the user can see them

function isUnitAlive(u: any): boolean {
  if (u.alive === false) return false;
  return u.hp == null || u.hp > 0;
}

// --------------------------------------------------------
// Pick the best action from the actions response.
// Priority: attack > move > first action available
// --------------------------------------------------------
function pickAction(actions: any): any | null {
  const attacks: any[] = actions.attacks || [];
  const moves: any[] = actions.moves || [];

  // Prefer attack
  if (attacks.length > 0 && attacks[0].action_id) {
    return { id: attacks[0].action_id, kind: "attack", data: attacks[0] };
  }
  // Then move
  if (moves.length > 0 && moves[0].action_id) {
    return { id: moves[0].action_id, kind: "move", data: moves[0] };
  }
  return null;
}

// --------------------------------------------------------
// Fetch state helper
// --------------------------------------------------------
async function fetchState(): Promise<any> {
  const res = await fetch(`${BACKEND}/api/game/state`);
  return res.json();
}

// --------------------------------------------------------
// Main runner — call after every human step
// --------------------------------------------------------
export async function runAiTurns(
  unitLayerRef: any
): Promise<void> {

  let state = await fetchState();

  // Keep running while the active side is AI
  while (state?.sides?.[state.active_side] === "ai") {

    const activeSide: string = state.active_side;
    const activatedUnits: string[] = state.activated_units || [];
    const units: any[] = state.units || [];

    // Find the first unit of the AI side that hasn't been activated yet
    const aiUnit = units.find(
      (u: any) =>
        u.side === activeSide &&
        isUnitAlive(u) &&
        !activatedUnits.includes(u.id)
    );

    if (!aiUnit) {
      // All AI units activated — nothing more to do this turn
      console.log("🤖 AI: all units activated, passing turn");
      break;
    }

    console.log(`🤖 AI: fetching actions for unit=${aiUnit.id} (type=${aiUnit.unit_key})`);

    // Fetch available actions for this unit
    let actions: any = { moves: [], attacks: [] };
    try {
      const res = await fetch(`${BACKEND}/api/game/actions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ unit_id: aiUnit.id }),
      });
      actions = await res.json();
    } catch (err) {
      console.warn("🤖 AI: error fetching actions", err);
      break;
    }

    const action = pickAction(actions);

    if (!action) {
      console.log(`🤖 AI: no valid action for ${aiUnit.id}, skipping`);
      break;
    }

    console.log(`🤖 AI: selected action=${action.id} (${action.kind}) for ${aiUnit.id}`);
    setUnitActionMarker(aiUnit.id, resolveActionMarker(action.data));
    
    // Log selection/action choice to the System Log panel
    if (action.kind === "move") {
      (window as any).logSystemEvent?.("move", `🤖 AI Order: Move ${aiUnit.id} to hex ${formatCoords(action.data.q, action.data.r)}`);
    } else if (action.kind === "attack") {
      (window as any).logSystemEvent?.("combat", `⚔️ AI Order: Combat attack by ${aiUnit.id} on target ${action.data.target_id}`);
    }

    // If it's a move, trigger the visual animation in Pixi before stepping
    if (action.kind === "move" && unitLayerRef?.current) {
      const { q, r } = action.data;
      await unitLayerRef.current.moveUnit(aiUnit.id, q, r);
    } else {
      // Visual delay for attacks or actions that don't animate movement
      await new Promise(r => setTimeout(r, AI_DELAY_MS));
    }

    // Execute the action in the backend
    let stepData: any = null;
    try {
      console.log(`🤖 AI stepping backend with action=${action.id}`);
      (window as any).logSystemEvent?.("system", `⚙️ AI step executed: Action ID ${action.id}`);
      const stepRes = await fetch(`${BACKEND}/api/game/step`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action_id: action.id }),
      });
      stepData = await stepRes.json();

      // Log AI combat results (damage + dice) straight from the step response,
      // so they are not lost to React batching when the state is pushed below.
      logCombatEvents(stepData?.state?.last_events, stepData?.state?.units || []);

      // Update local state directly with step response if available
      state = stepData.state || await fetchState();
    } catch (err) {
      console.warn("🤖 AI: step failed", err);
      break;
    }

    // Trigger Combat FX if there are combat events in this step
    if (action.kind === "attack" && stepData?.state?.last_events) {
      const combatEvent = stepData.state.last_events.find((e: any) => e.type === "ACTION_EFFECT");
      if (combatEvent && unitLayerRef?.current) {
        const fxLayer = unitLayerRef.current.container?.parent?.children.find(
          (c: any) => c.label === "fxLayer"
        ) || unitLayerRef.current.container?.parent; // fallback to parent if not found

        const defenderUnit = state.units.find((u: any) => u.id === action.data.target_id);

        if (fxLayer && defenderUnit) {
          const { playCombatFX } = await import("../animation/combatFx");
          await playCombatFX(
            fxLayer,
            { q: aiUnit.q, r: aiUnit.r },
            { q: defenderUnit.q, r: defenderUnit.r },
            combatEvent.payload?.attack_dice || ["DAMAGE"],
            combatEvent.payload?.defense_dice || []
          );
        }
      }
    }

    // Push state update to Controller so all UI components, status lists, and logs react
    gameController.updateState(state);
    
    // Also call global setter for Pixi canvas
    (window as any).__setGameState?.(state);

    console.log(`🤖 AI: turn step completed, active_side=${state.active_side}`);
    
    // Short pause between AI unit activations
    await new Promise(r => setTimeout(r, 400));
  }

  // Push final state when exiting loop
  if (state) {
    gameController.updateState(state);
    (window as any).__setGameState?.(state);
  }
}
