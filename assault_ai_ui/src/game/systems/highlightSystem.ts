// File: systems/highlightSystem.ts

export function updateHighlights(
  layer: any,
  data: any,
  selectedUnitId: string | null,
  availableMoves: any[],
  hoverHex: { q: number; r: number } | null
) {
  if (!layer || !data) return;

  layer.clear();

  // 1. Find selected unit position
  let selectedUnit: any = null;

  if (selectedUnitId) {
    selectedUnit = data.units?.find((u: any) => u.id === selectedUnitId);

    if (selectedUnit) {
      layer.drawSelected(selectedUnit.q, selectedUnit.r);
    }
  }

  // 2. Draw all valid move/attack destinations
  const moves   = availableMoves.filter((m: any) => m.kind !== "attack");
  const attacks = availableMoves.filter((m: any) => m.kind === "attack");

  if (moves.length > 0)   layer.drawMoves(moves);
  if (attacks.length > 0) layer.drawAttacks(attacks);

  // 3. Draw hover highlight + directional arrow from unit to hovered hex
  if (hoverHex && selectedUnit) {
    const isValidMove   = moves.some(  (m: any) => m.q === hoverHex.q && m.r === hoverHex.r);
    const isValidAttack = attacks.some((a: any) => a.q === hoverHex.q && a.r === hoverHex.r);

    if (isValidMove || isValidAttack) {
      layer.drawHover(hoverHex.q, hoverHex.r);
      layer.drawArrow(
        selectedUnit.q, selectedUnit.r,
        hoverHex.q,     hoverHex.r,
        isValidAttack
      );
    }
  }
}