// src/combat/RangedCombatPanel.tsx
//
// RangedCombatPanel
//
// Responsibility:
// - Render a single RangedCombat ACTION_EFFECT.
// - Pure presentation.
// - Replay-driven.
// - NO game logic.

import React from "react";
import { CombatDiceRow } from "./CombatDiceRow";

interface RangedCombatPanelProps {
  payload: any; // comes directly from replay
  unitLabel: (unitId: string) => string;
}

export const RangedCombatPanel: React.FC<RangedCombatPanelProps> = ({
  payload,
  unitLabel,
}) => {
  const attackerId = payload.attacker;
  const defenderId = payload.defender;

  const attackerLabel = attackerId ? unitLabel(attackerId) : "?";
  const defenderLabel = defenderId ? unitLabel(defenderId) : "?";

  const distance = payload.distance;
  const sector = payload.attack_sector;

  const attackerAttackDice = payload.attacker_attack_dice ?? [];
  const defenderDefenseDice = payload.defender_defense_dice ?? [];

  const hpBefore = payload.defender_hp_before;
  const hpAfter = payload.defender_hp_after;

  const attackerEffects = payload.attacker_effects ?? {};
  const criticals = attackerEffects.criticals ?? [];
  const suppress = attackerEffects.suppress ?? 0;

  const defenderKilled = payload.defender_killed === true;

  return (
    <div className="ranged-combat-panel">
      {/* Header */}
      <div className="combat-header">
        🎯 Ranged Combat
      </div>

      {/* Attacker → Defender */}
      <div className="combat-subheader">
        {attackerLabel} → {defenderLabel}
        {" "}
        <span className="combat-meta">
          (dist {distance}, sector {sector})
        </span>
      </div>

      {/* Dice */}
      <CombatDiceRow
        label="Attacker attack"
        dice={attackerAttackDice}
      />

      <CombatDiceRow
        label="Defender defense"
        dice={defenderDefenseDice}
      />

      {/* Damage */}
      {hpBefore !== undefined && hpAfter !== undefined && (
        <div className="combat-damage">
          {hpBefore > hpAfter ? (
            <span>
              {defenderLabel}: -{hpBefore - hpAfter} HP
              {" "}
              ({hpBefore} → {hpAfter})
            </span>
          ) : (
            <span>
              No damage applied
            </span>
          )}
        </div>
      )}

      {/* Criticals */}
      {criticals.length > 0 && (
        <div className="combat-criticals">
          💥 Critical hits: {criticals.length}
        </div>
      )}

      {/* Suppression */}
      {suppress > 0 && (
        <div className="combat-suppress">
          😵 Suppressed
        </div>
      )}

      {/* Kill */}
      {defenderKilled && (
        <div className="combat-kill">
          ☠️ {defenderLabel} DESTROYED
        </div>
      )}
    </div>
  );
};