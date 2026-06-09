export type ActionMarkerType =
  | "normal"
  | "fast_action"
  | "firing"
  | "turret_firing"
  | "move_fire"
  | "fire_move";

const MARKER_BASE = "/art/action_markers";

export const actionMarkerImages: Record<ActionMarkerType, string> = {
  normal: `${MARKER_BASE}/normal.png`,
  fast_action: `${MARKER_BASE}/fast_action.png`,
  firing: `${MARKER_BASE}/firing.png`,
  turret_firing: `${MARKER_BASE}/turret_firing.png`,
  move_fire: `${MARKER_BASE}/move_fire.png`,
  fire_move: `${MARKER_BASE}/fire_move.png`,
};

type UnitActionMarkerStore = Record<string, ActionMarkerType>;

function getStore(): UnitActionMarkerStore {
  const w = window as any;
  if (!w.__unitActionMarkers) {
    w.__unitActionMarkers = {};
  }
  return w.__unitActionMarkers as UnitActionMarkerStore;
}

export function clearUnitActionMarkers(): void {
  (window as any).__unitActionMarkers = {};
}

export function setUnitActionMarker(unitId: string, marker: ActionMarkerType): void {
  if (!unitId) return;
  const store = getStore();
  store[unitId] = marker;
}

export function getUnitActionMarker(unitId: string): ActionMarkerType | null {
  if (!unitId) return null;
  const store = getStore();
  return store[unitId] || null;
}

export function resolveActionMarker(actionLike: any): ActionMarkerType {
  const type = String(actionLike?.type || actionLike?.kind || actionLike?.action || "").toUpperCase();
  const actionId = String(actionLike?.action_id || "").toUpperCase();

  if (type.includes("MOVE_THEN_FIRE") || actionId.startsWith("MOVE_FIRE:")) {
    return "move_fire";
  }
  if (type.includes("FIRE_THEN_MOVE") || actionId.startsWith("FIRE_MOVE:")) {
    return "fire_move";
  }
  if (type.includes("INDIRECT") || actionId.includes("RANGED_INDIRECT")) {
    return "turret_firing";
  }
  if (
    type.includes("RANGED") ||
    type.includes("ATTACK") ||
    type.includes("ASSAULT") ||
    type.includes("FIRE") ||
    actionId.startsWith("RANGED_DIRECT:")
  ) {
    return "firing";
  }
  if (type.includes("FAST") || actionId.includes(":FAST")) {
    return "fast_action";
  }
  return "normal";
}
