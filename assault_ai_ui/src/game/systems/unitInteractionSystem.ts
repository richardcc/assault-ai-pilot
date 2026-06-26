import { apiUrl } from "../../config/backend";

function resolveUnitHex(unit: any): { q?: number; r?: number } {
  if (!unit) return {};
  const q = unit.q ?? unit.position?.q;
  const r = unit.r ?? unit.position?.r;
  return { q, r };
}

export async function handleUnitClick(
  unit: any,
  state: any,
  setAvailableMoves: (moves: any[]) => void,
  setAttackHint: (hint: string | null) => void
) {

  if (!state) return;

  const hp = unit.hp;
  if (unit.alive === false || (hp != null && hp <= 0)) {
    setAttackHint("Unit is destroyed");
    return;
  }

  const isHumanTurn =
    state?.sides?.[state.active_side] === "human";

  if (!isHumanTurn) {
    setAttackHint("Not human turn");
    return;
  }

  const id = unit.unit_id ?? unit.id;

  const isAvailable =
    unit.side === state.active_side &&
    !state.activated_units?.includes(id) &&
    unit.alive !== false &&
    (unit.hp == null || unit.hp > 0);

  if (!isAvailable) {
    const activeSide = String(state?.active_side || "");
    const reason =
      unit.side !== state.active_side
        ? `Not this side's turn (active: ${activeSide || "?"})`
        : state.activated_units?.includes(id)
        ? "Unit already activated this turn"
        : "Unit not available";
    setAttackHint(reason);
    return;
  }

  console.log("✅ selected:", id);

  (window as any).selectUnit?.(id);

  // ✅ clear previous
  setAvailableMoves([]);
  setAttackHint(null);

  const res = await fetch(apiUrl("/api/game/actions"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ unit_id: id })
  });

  const actions = await res.json();

  console.log("🎯 actions:", actions);

  const allActions = [
    ...(actions.attacks || []).map(a => {
      const target = state.units?.find(
        (u: any) => u.id === a.target_id || u.unit_id === a.target_id
      );
      const targetPos = resolveUnitHex(target);
      const targetHex = (a as any).target_hex;
      const moveTo = (a as any).move_to;

      return {
        ...a,
        kind: "attack",
        q: targetPos.q ?? targetHex?.[0],
        r: targetPos.r ?? targetHex?.[1],
        move_q: moveTo?.q,
        move_r: moveTo?.r,
      };
    }),
    ...(actions.moves || []).map(m => ({
      ...m,
      kind: "move"
    })),
    ...(actions.waits || []).map(w => ({
      ...w,
      kind: "wait"
    }))
  ];

  setAvailableMoves(allActions);
  const attackStatus = actions.attack_status;
  if (attackStatus?.can_attack === false) {
    setAttackHint(
      `${attackStatus.reason_code || "no_attack"}: ${attackStatus.reason_text || "No attack available"}`
    );
  } else {
    setAttackHint(null);
  }
}