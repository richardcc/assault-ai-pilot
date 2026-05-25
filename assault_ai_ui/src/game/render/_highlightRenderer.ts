// File: C:\repos\python\assault\assault_ai_ui\src\game\render\highlightRenderer.ts

export function renderHighlights(
  state: any,
  actions: any,
  selectedUnitId: string,
  drawHex: (q: number, r: number, color: string) => void,
) {

  if (!state || !selectedUnitId) return;

  const unit = state.units.find((u: any) => u.id === selectedUnitId);
  if (!unit) return;

  // 🟢 selected unit
  drawHex(unit.q, unit.r, "green");

  if (!actions) return;

  // 🔵 moves
  actions.moves?.forEach((h: any) => {
    drawHex(h.q, h.r, "blue");
  });

  // 🔴 attacks
  actions.attacks?.forEach((a: any) => {
    const target = state.units.find((u: any) => u.id === a.target_id);
    if (target) {
      drawHex(target.q, target.r, "red");
    }
  });
}
