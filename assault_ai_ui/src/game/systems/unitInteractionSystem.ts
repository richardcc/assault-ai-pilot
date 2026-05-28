export async function handleUnitClick(
  unit: any,
  state: any,
  setAvailableMoves: (moves: any[]) => void
) {

  if (!state) return;

  const isHumanTurn =
    state?.sides?.[state.active_side] === "human";

  if (!isHumanTurn) return;

  const id = unit.unit_id ?? unit.id;

  const isAvailable =
    unit.side === state.active_side &&
    !state.activated_units?.includes(id);

  if (!isAvailable) return;

  console.log("✅ selected:", id);

  (window as any).selectUnit?.(id);

  // ✅ clear previous
  setAvailableMoves([]);

  const res = await fetch("http://127.0.0.1:8000/api/game/actions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ unit_id: id })
  });

  const actions = await res.json();

  console.log("🎯 actions:", actions);

  const allActions = [
    ...(actions.moves || []).map(m => ({
      ...m,
      kind: "move"
    })),
    ...(actions.attacks || []).map(a => ({
      ...a,
      kind: "attack"
    }))
  ];

  setAvailableMoves(allActions);
}