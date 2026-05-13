function renderRangedCombat(payload, unitLabel) {
  console.log("⚔️ renderRangedCombat called", payload);

  const atk = unitLabel(payload.attacker);
  const def = unitLabel(payload.defender);

  // ---------------------------
  // Highlight attacker / defender hexes on the map
  // ---------------------------
  if (
    typeof getUnitHexPosition === "function" &&
    typeof highlightHexPair === "function"
  ) {
    const attackerPos = getUnitHexPosition(payload.attacker);
    const defenderPos = getUnitHexPosition(payload.defender);

    if (attackerPos && defenderPos) {
      highlightHexPair(
        attackerPos.q,
        attackerPos.r,
        defenderPos.q,
        defenderPos.r,
        grid,
        app
      );
    }
  }

  // ---------------------------
  // Build combat HTML (REAL HTML)
  // ---------------------------
  let html = `
    <div class="combat-header">
      <div class="combat-header-title">⚔️ RANGED COMBAT</div>

      <div class="combat-focus">
        <strong>${atk}</strong> → <strong>${def}</strong><br/>
        <span class="combat-meta">
          Distance ${payload.distance} · ${payload.attack_sector}
        </span>
      </div>
    </div>

    <!-- ✅ TWO COLUMN GRID -->
    <div class="combat-dice-grid">

      <div class="combat-dice-col">
        <div class="combat-side-title">ATTACK</div>
        ${renderDiceRow("", payload.attacker_attack_dice)}
      </div>

      <div class="combat-dice-col">
        <div class="combat-side-title">DEFENSE</div>
        ${renderDiceRow("", payload.defender_defense_dice)}
      </div>

    </div>

    <div class="combat-body">
  `;

  if (
    payload.defender_hp_before !== undefined &&
    payload.defender_hp_after !== undefined
  ) {
    const delta =
      payload.defender_hp_before - payload.defender_hp_after;

    if (delta > 0) {
      html += `
        <div class="combat-damage">
          ${def}: -${delta} HP
          (${payload.defender_hp_before} → ${payload.defender_hp_after})
        </div>
      `;
    }
  }

  const crits = payload.attacker_effects?.criticals ?? [];
  if (crits.length > 0) {
    html += `
      <div class="combat-crit">
        💥 Critical hits: ${crits.length}
      </div>
    `;
  }

  if (payload.defender_killed) {
    html += `
      <div class="combat-kill">
        ☠️ ${def} DESTROYED
      </div>
    `;
  }

  html += `</div>`; // combat-body

  return html;
}

// Expose globally
window.renderRangedCombat = renderRangedCombat;