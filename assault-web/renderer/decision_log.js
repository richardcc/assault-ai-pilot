/* =========================================================
   Decision Log Renderer
   ========================================================= */

const RATIONALE_TEXT = {
  0: "Mantener posición (esperar)",
  1: "Avanzar para ganar terreno",
  2: "Atacar al enemigo",
  3: "Retirada por riesgo elevado",
  4: "Defensa prioritaria"
};

function explainRationale(action, rationaleId) {
  if (rationaleId === 0 && action !== "WAIT") {
    return "Mantener seguridad sin comprometerse (reposicionamiento)";
  }

  if (rationaleId === 1 && action === "WAIT") {
    return "Preparar avance sin exponerse";
  }

  if (rationaleId === 4 && action.startsWith("MOVE")) {
    return "Reposicionamiento defensivo";
  }

  return RATIONALE_TEXT[rationaleId] ?? `Rationale ${rationaleId}`;
}

function hexToLabel(hex) {
  if (!hex) return "?";

  if (typeof hex === "string" && /^[A-Z]\d+$/.test(hex)) {
    return hex;
  }

  if (typeof hex === "string") {
    const m = hex.match(/-?\d+/g);
    if (m && m.length >= 2) {
      const col = parseInt(m[0], 10);
      const row = parseInt(m[1], 10);
      return `${String.fromCharCode(65 + col)}${row + 1}`;
    }
  }

  if (Array.isArray(hex) && hex.length >= 2) {
    return `${String.fromCharCode(65 + hex[0])}${hex[1] + 1}`;
  }

  return "?";
}

function findUnit(units, unitId) {
  return units.find(u => u.unit_id === unitId);
}

/* ✅ DEFAULT EXPORT */
export default function renderDecisionLog(
  logFn,
  decision,
  state,
  prevState
) {
  if (!decision) return;

  const d = decision;

  const tag =
    d.agent_type === "RL" ? "[RL]" :
    d.agent_type === "HEURISTIC" ? "[HEU]" :
    "[AI]";

  logFn(`${tag} ${d.actor} → ${d.action}`);

  if (d.agent_type === "RL" && d.learned_rationale !== null) {
    logFn(
      `    ↳ Rationale: ${explainRationale(d.action, d.learned_rationale)}`
    );
  }

  if (d.agent_type === "HEURISTIC" && d.heuristic_rationale) {
    logFn(`    ↳ Heuristic rule: ${d.heuristic_rationale}`);
  }

  if (!prevState) return;

  const prevUnit = findUnit(prevState.units, d.actor);
  const currUnit = findUnit(state.units, d.actor);

  if (!prevUnit || !currUnit) return;

  if (prevUnit.hex !== currUnit.hex) {
    logFn(
      `    ↳ Move: ${hexToLabel(prevUnit.hex)} → ${hexToLabel(currUnit.hex)}`
    );
  }

  if (prevUnit.strength !== currUnit.strength) {
    logFn(
      `    ↳ Strength: ${prevUnit.strength} → ${currUnit.strength}`
    );
  }
}