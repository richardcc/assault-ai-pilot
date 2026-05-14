// ---------------------------------------------
// ✅ APPLY ONE EVENT
// ---------------------------------------------
function applySingleEvent(gameState, event) {
  if (!event) return;

  switch (event.type) {

    case "UNIT_MOVED": {
      const { unit_id, to } = event.payload;
      const unit = gameState.units[unit_id];
      if (!unit || !unit.position) return;

      unit.position.q = to.q;
      unit.position.r = to.r;
      break;
    }

    case "ACTION_EFFECT": {
      const p = event.payload;
      const unit = gameState.units[p.defender];
      if (!unit) return;

      if (typeof p.defender_hp_after === "number") {
        unit.hp = p.defender_hp_after;
      }

      unit.alive = !p.defender_killed;
      break;
    }
  }
}

// ---------------------------------------------
// ✅ BUILD STRATEGIC STATE
// ---------------------------------------------
function buildStrategicState(gameState, unitId) {
  let friendly = 0;
  let enemy = 0;

  const prefix = unitId.split("_")[0];

  for (const [id, u] of Object.entries(gameState.units)) {
    if (!u || !u.alive) continue;

    if (id.startsWith(prefix)) {
      friendly += u.hp || 1;
    } else {
      enemy += u.hp || 1;
    }
  }

  const unit = gameState.units[unitId];

  let distance = 0;
  if (unit?.position) {
    distance = Math.abs(unit.position.q) + Math.abs(unit.position.r);
  }

  return {
    friendly_strength: String(friendly),
    enemy_pressure: String(enemy),
    objective_distance: String(distance)
  };
}

// -------------------------------------------------
// ✅ APPLY RANGE
// -------------------------------------------------
window.applyEventRange = function applyEventRange(
  gameState,
  turnIndex,
  fromEventIndex,
  toEventIndex
) {
  const turn = gameState.replay.turns[turnIndex];
  if (!turn) return;

  hideCombatPanel?.();

  clearHRLExplanation?.();
  clearTacticalExplanation?.();

  let combatPayload = null;
  let lastPayload = null;

  for (let i = fromEventIndex; i < toEventIndex; i++) {
    const event = turn.events[i];
    if (!event) continue;

    // ✅ Apply state changes
    applySingleEvent(gameState, event);

    const unitId =
      event.payload?.unit_id ||
      event.payload?.attacker ||
      event.payload?.active_unit;

    if (!unitId) continue;

    // ✅ acción REAL (no genérica)
    const action = event.payload?.action || event.type;

    const state = buildStrategicState(gameState, unitId);
    const friendly = Number(state.friendly_strength);
    const enemy = Number(state.enemy_pressure);

    // ✅ FIX CRÍTICO: guardar texto real SIEMPRE
    window.lastRealText = `${unitId} performs ${action} (${friendly} vs ${enemy})`;

    // ✅ payload correcto para backend
    lastPayload = {
      activation: {
        unit_id: unitId,
        action: action,
        target: event.payload?.defender || null,
        events: [event],
        strategic_state: state
      }
    };

    // ✅ UI rápida (sin inventar)
    renderHRLExplanation({
      strategic_intent: {
        explanation: window.lastRealText
      }
    });

    if (event.type === "ACTION_EFFECT") {
      combatPayload = event.payload;
    }
  }

  // ✅ guardar solo UNA vez (para botón)
  if (lastPayload) {
    window.lastExplainPayload = lastPayload;
  }

  // -------------------------------------------------
  // ✅ Combat visuals
  // -------------------------------------------------
  if (
    combatPayload &&
    typeof renderRangedCombat === "function" &&
    typeof showCombatPanel === "function"
  ) {
    const html = renderRangedCombat(
      combatPayload,
      unitId => unitId
    );

    setTimeout(() => {
      showCombatPanel(html);

      const attackerUnit = gameState.units[combatPayload.attacker];
      const defenderUnit = gameState.units[combatPayload.defender];

      if (
        attackerUnit &&
        defenderUnit &&
        typeof animateUnitAttack === "function" &&
        window.mapEntityLayerSprites
      ) {
        const attackerSprite =
          mapEntityLayerSprites.getUnitSprite(combatPayload.attacker);

        const layer = attackerSprite?.parent;

        if (layer) {
          const grid = {
            R: HexGeometry.R,
            ROW: HexGeometry.ROW ?? (1.5 * HexGeometry.R),
            W: HexGeometry.W ?? (Math.sqrt(3) * HexGeometry.R)
          };

          animateUnitAttack(
            attackerUnit.position.q,
            attackerUnit.position.r,
            defenderUnit.position.q,
            defenderUnit.position.r,
            grid,
            layer,
            PIXI.Ticker.shared,
            800
          );
        }
      }

      const panel = document.getElementById("combat-panel");
      if (panel && typeof animateCombatDice === "function") {
        animateCombatDice(
          panel,
          combatPayload.attacker_attack_dice,
          600
        );
      }

      playCombatGunshot?.();

    }, 0);
  }

  // -------------------------------------------------
  // ✅ 🔥 FIX CLAVE: REFRESH UI
  // -------------------------------------------------
  // Garantiza que la vista (cards, posiciones, etc.)
  // se actualice tras cambiar el estado
  if (typeof renderFrame === "function") {
    requestAnimationFrame(() => {
      try {
        renderFrame(gameState, window.UI_STATE);
      } catch (e) {
        console.warn("[UI REFRESH] Failed:", e);
      }
    });
  }
};