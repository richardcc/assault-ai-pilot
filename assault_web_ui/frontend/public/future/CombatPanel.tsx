// src/combat/CombatPanel.tsx
//
// CombatPanel
//
// Responsibility:
// - Orchestrate combat rendering.
// - Decide which combat panel to show based on ACTION_EFFECT.
// - NO game logic.
// - Replay-driven only.

import React from "react";
import { RangedCombatPanel } from "./RangedCombatPanel";
import { CloseCombatPanel } from "./CloseCombatPanel";

interface CombatPanelProps {
  event: {
    type: string;
    payload: any;
  };
  unitLabel: (unitId: string) => string;
}

export const CombatPanel: React.FC<CombatPanelProps> = ({
  event,
  unitLabel,
}) => {
  if (!event || event.type !== "ACTION_EFFECT") {
    return null;
  }

  const payload = event.payload;
  const action = payload?.action;

  switch (action) {
    case "RangedCombat":
      return (
        <RangedCombatPanel
          payload={payload}
          unitLabel={unitLabel}
        />
      );

    case "CloseCombat":
      return (
        <CloseCombatPanel
          payload={payload}
          unitLabel={unitLabel}
        />
      );

    default:
      // Unknown ACTION_EFFECT → intentionally ignored
      return null;
  }
};