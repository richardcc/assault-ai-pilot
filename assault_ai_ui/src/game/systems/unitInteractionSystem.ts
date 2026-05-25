// File: C:\repos\python\assault\assault_ai_ui\src\game\systems\unitInteractionSystem.ts

export async function handleUnitClick(
  unit: any,
  state: any,
  setAvailableMoves: (moves: any[]) => void
) {

  if (!state) return;

  const isHumanTurn =
    state?.sides?.[state.active_side] === "human";

  if (!isHumanTurn) return;

  const isAvailable =
    unit.side === state.active_side &&
    !state.activated_units?.includes(unit.id);

  if (!isAvailable) return;

  console.log("✅ selected:", unit.id);

  (window as any).selectUnit?.(unit.id);

  // ✅ clear previous
  setAvailableMoves([]);

  // ✅ backend call
  const res = await fetch("http://127.0.0.1:8000/api/game/actions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ unit_id: unit.id })
  });

  const actions = await res.json();

  console.log("🎯 actions:", actions);

  setAvailableMoves(actions.moves || []);
}