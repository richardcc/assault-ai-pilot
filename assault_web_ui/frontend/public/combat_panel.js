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

    <div class="combat-sides">
      <div class="combat-side attacker">
        <div class="combat-side-title">ATTACKER</div>
        ${renderDiceRow("Attack", payload.attacker_attack_dice)}
      </div>

      <div class="combat-side defender">
        <div class="combat-side-title">DEFENDER</div>
        ${renderDiceRow("Defense", payload.defender_defense_dice)}
      </div>
    </div>
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
    html += `<div class="combat-crit">💥 Critical hits: ${crits.length}</div>`;
  }

  if (payload.defender_killed) {
    html += `<div class="combat-kill">☠️ ${def} DESTROYED</div>`;
  }

  return html;
}