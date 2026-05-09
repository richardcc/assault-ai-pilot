// src/combat/CombatDiceRow.tsx
//
// CombatDiceRow
//
// Responsibility:
// - Render a horizontal row of dice sprites.
// - NO game logic.
// - NO combat rules.
// - Uses diceSpriteResolver for mapping.
//
// Props contract:
//   dice: Array<{ color: DiceColor; faces: DiceFace[] }>

import React from "react";
import { DiceResultDTO, getDiceSprite } from "./diceSpriteResolver";

import "./CombatDiceRow.css";

interface CombatDiceRowProps {
  label?: string;
  dice: DiceResultDTO[];
}

export const CombatDiceRow: React.FC<CombatDiceRowProps> = ({
  label,
  dice,
}) => {
  if (!dice || dice.length === 0) {
    return null;
  }

  return (
    <div className="combat-dice-row">
      {label && (
        <div className="combat-dice-label">
          {label}
        </div>
      )}

      <div className="combat-dice-list">
        {dice.map((die, index) => (
          <img
            key={index}
            src={`/assets/dice/${getDiceSprite(die)}`}
            alt={`${die.color} die`}
            className="combat-die"
          />
        ))}
      </div>
    </div>
  );
};