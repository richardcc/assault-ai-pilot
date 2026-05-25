// File: C:\repos\python\assault\assault_ai_ui\src\game\ui\useGameSelection.ts

import { useState } from "react";

export function useGameSelection() {

  const [selectedUnit, setSelectedUnit] = useState<string | null>(null);
  const [actions, setActions] = useState<any>(null);

  return {
    selectedUnit,
    setSelectedUnit,
    actions,
    setActions
  };
}
