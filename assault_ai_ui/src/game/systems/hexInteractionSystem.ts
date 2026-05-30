import { axialToPixel, HEX_SIZE } from "../render/hexGridRenderer";
import { animateMove } from "../animation/animateMove";

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

  // Find the unit container in the Pixi scene
  const unitContainer = unitLayerRef.current?.container?.children.find(
    (c: any) => c.__unitId === selectedUnitId
  );

  if (!unitContainer) {
    console.warn("❌ unit container not found:", selectedUnitId);
    return;
  }

  // Block double-dispatch while animating
  if (unitContainer.__isMoving) {
    console.warn("⛔ MOVE BLOCKED: already moving", selectedUnitId);
    return;
  }

  // Convert axial hex to pixel centre
  const { x, y } = axialToPixel(q, r);
  const to = {
    x: Math.round(x),
    y: Math.round(y + HEX_SIZE),
  };

  console.log("🎬 animating move", { id: selectedUnitId, to });

  // Run animation, then POST to backend
  await new Promise<void>((resolve) => {
    animateMove(unitContainer, to, null as any, 380, resolve);
  });

  console.log("✅ animation complete, posting to backend");

  // Dispatch step to backend
  await fetch("http://127.0.0.1:8000/api/game/step", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action_id: actionId }),
  });

  // Pull fresh state and push to canvas
  const res = await fetch("http://127.0.0.1:8000/api/game/state");
  const newState = await res.json();

  setSelectedUnitId(null);
  setAvailableMoves([]);
  (window as any).__setGameState?.(newState);
}
