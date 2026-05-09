function renderRangedCombat(payload, unitLabel) {
  const atk = unitLabel(payload.attacker);
  const def = unitLabel(payload.defender);

  let html = `
    <div class="combat-header">🎯 RANGED COMBAT</div>
    <div class="combat-subheader">
      ${atk} → ${def}
      <span class="combat-meta">
        (dist ${payload.distance}, sector ${payload.attack_sector})
      </span>
    </div>
  `;

  html += renderDiceRow(
    "Attacker attack",
    payload.attacker_attack_dice
  );

  html += renderDiceRow(
    "Defender defense",
    payload.defender_defense_dice
  );

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
    html += `<div class="combat-crit">💥 Critical hits: ${crits.length}</div>`;
  }

  if (payload.defender_killed) {
    html += `<div class="combat-kill">☠️ ${def} DESTROYED</div>`;
  }

  return html;
}
