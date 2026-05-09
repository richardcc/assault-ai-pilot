// src/combat/CloseCombatPanel.tsx
//
// CloseCombatPanel
//
// Responsibility:
// - Render a CloseCombat ACTION_EFFECT.
// - Render multiple combat rounds.
// - Pure presentation.
// - Replay-driven.
// - NO game logic.

import React from "react";
import { CombatDiceRow } from "./CombatDiceRow";

interface CloseCombatPanelProps {
  payload: any; // CloseCombat ACTION_EFFECT payload
  unitLabel: (unitId: string) => string;
}

export const CloseCombatPanel: React.FC<CloseCombatPanelProps> = ({
  payload,
  unitLabel,
}) => {
  const attackerId = payload.attacker;
  const defenderId = payload.defender;

  const attackerLabel = attackerId ? unitLabel(attackerId) : "?";
  const defenderLabel = defenderId ? unitLabel(defenderId) : "?";

  const rounds = payload.rounds ?? [];
  const outcome = payload.outcome;

  return (
    <div className="close-combat-panel">
      {/* Header */}
      <div className="combat-header">
        💥 Close Combat
      </div>

      {/* Attacker vs Defender */}
      <div className="combat-subheader">
        {attackerLabel} vs {defenderLabel}
      </div>

      {/* Rounds */}
      {rounds.map((round: any) => (
        <div
          key={round.round}
          className="close-combat-round"
        >
          <div className="close-combat-round-title">
            Round {round.round}
          </div>

          <CombatDiceRow
            label="Attacker attack"
            dice={round.attacker_attack_dice}
          />

          <CombatDiceRow
            label="Attacker defense"
            dice={round.attacker_defense_dice}
          />

          <CombatDiceRow
            label="Defender attack"
            dice={round.defender_attack_dice}
          />

          <CombatDiceRow
            label="Defender defense"
            dice={round.defender_defense_dice}
          />

          {/* Damage this round */}
          <div className="combat-damage">
            {renderRoundDamage(
              round,
              attackerId,
              defenderId,
              unitLabel
            )}
          </div>
        </div>
      ))}

      {/* Outcome */}
      {outcome && (
        <div className="combat-outcome">
          Result: {outcome}
        </div>
      )}
    </div>
  );
};

// -------------------------------------------------
// Helpers (presentation only)
// -------------------------------------------------

function renderRoundDamage(
  round: any,
  attackerId: string,
  defenderId: string,
  unitLabel: (id: string) => string
) {
  const lines: string[] = [];

  if (
    round.attacker_hp_before !== undefined &&
    round.attacker_hp_after !== undefined
  ) {
    const delta =
      round.attacker_hp_before - round.attacker_hp_after;
    if (delta > 0) {
      lines.push(
        `${unitLabel(attackerId)}: -${delta} HP ` +
          `(${round.attacker_hp_before} → ${round.attacker_hp_after})`
      );
    }
  }

  if (
    round.defender_hp_before !== undefined &&
    round.defender_hp_after !== undefined
  ) {
    const delta =
      round.defender_hp_before - round.defender_hp_after;
    if (delta > 0) {
      lines.push(
        `${unitLabel(defenderId)}: -${delta} HP ` +
          `(${round.defender_hp_before} → ${round.defender_hp_after})`
      );
    }
  }

  if (lines.length === 0) {
    return <span>No damage applied</span>;
  }

  return (
    <ul>
      {lines.map((line, idx) => (
        <li key={idx}>{line}</li>
      ))}
    </ul>
  );
}