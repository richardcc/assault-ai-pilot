// ---------------------------------------------
// ✅ APPLY ONE EVENT (DETERMINISTIC STATE UPDATE)
// ---------------------------------------------
function applySingleEvent(gameState, event) {
  if (!event) return;

  switch (event.type) {

    // -------------------------------------------------
    // ✅ UNIT MOVEMENT (FIX)
    // -------------------------------------------------
    case "UNIT_MOVED": {
      const { unit_id, to } = event.payload;
      const unit = gameState.units[unit_id];
      if (!unit) return;

      // ✅ mantener coords planas (no rompe nada)
      unit.q = to.q;
      unit.r = to.r;

      // ✅ 🔥 FIX CRÍTICO → ACTUALIZA POSITION
      unit.position = {
        q: to.q,
        r: to.r
      };

      break;
    }

    // -------------------------------------------------
    // ✅ COMBAT RESULT (DAMAGE + STATUS)
    // -------------------------------------------------
    case "ACTION_EFFECT": {
      const p = event.payload;
      const unit = gameState.units[p.defender];
      if (!unit) return;

      // ✅ HP update
      if (typeof p.defender_hp_after === "number") {
        unit.hp = p.defender_hp_after;
      }

      // ✅ Alive
      unit.alive = unit.hp > 0;

      // ✅ Suppression
      if (p.resolution?.remaining_suppress > 0) {
        unit.status = unit.status || [];

        if (!unit.status.includes("SUPPRESSED")) {
          unit.status.push("SUPPRESSED");
        }
      }

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
  if (unit) {
    distance = Math.abs(unit.q || 0) + Math.abs(unit.r || 0);
  }

  return {
    friendly_strength: String(friendly),
    enemy_pressure: String(enemy),
    objective_distance: String(distance)
  };
}


// -------------------------------------------------
// ✅ APPLY RANGE OF EVENTS (MAIN DRIVER)
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
  let lastUnitId = null;

  for (let i = fromEventIndex; i < toEventIndex; i++) {
    const event = turn.events[i];
    if (!event) continue;

    // ✅ APPLY EVENT
    applySingleEvent(gameState, event);

    const unitId =
      event.payload?.unit_id ||
      event.payload?.attacker ||
      event.payload?.active_unit;

    if (!unitId) continue;

    lastUnitId = unitId;

    const action = event.payload?.action || event.type;

    const state = buildStrategicState(gameState, unitId);
    const friendly = Number(state.friendly_strength);
    const enemy = Number(state.enemy_pressure);

    window.lastRealText = `${unitId} performs ${action} (${friendly} vs ${enemy})`;

    lastPayload = {
      activation: {
        unit_id: unitId,
        action: action,
        target: event.payload?.defender || null,
        events: [event],
        strategic_state: state
      }
    };

    renderHRLExplanation({
      strategic_intent: {
        explanation: window.lastRealText
      }
    });

    if (event.type === "ACTION_EFFECT") {
      combatPayload = event.payload;
    }
  }

  if (lastPayload) {
    window.lastExplainPayload = lastPayload;
  }

  // ✅ COMBAT VISUALS (SIN CAMBIOS)
  if (
    combatPayload &&
    lastUnitId &&
    typeof renderRangedCombat === "function" &&
    typeof showCombatPanel === "function"
  ) {
    const html = renderRangedCombat(
      combatPayload,
      id => id
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
            attackerUnit.q,
            attackerUnit.r,
            defenderUnit.q,
            defenderUnit.r,
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

  // ✅ REFRESH
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
