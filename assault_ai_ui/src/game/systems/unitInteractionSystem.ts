export async function handleUnitClick(
  unit: any,
  state: any,
  setAvailableMoves: (moves: any[]) => void
) {

  if (!state) return;

  const hp = unit.hp;
  if (unit.alive === false || (hp != null && hp <= 0)) {
    return;
  }

  const isHumanTurn =
    state?.sides?.[state.active_side] === "human";

  if (!isHumanTurn) return;

  const id = unit.unit_id ?? unit.id;

  const isAvailable =
    unit.side === state.active_side &&
    !state.activated_units?.includes(id) &&
    unit.alive !== false &&
    (unit.hp == null || unit.hp > 0);

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
    ...(actions.attacks || []).map(a => {
      const target = state.units?.find(
        (u: any) => u.id === a.target_id || u.unit_id === a.target_id
      );

      return {
        ...a,
        kind: "attack",
        q: target?.q,
        r: target?.r,
      };
    })
  ];

  setAvailableMoves(allActions);
}