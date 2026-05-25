// File: systems/highlightSystem.ts

export function updateHighlights(
  layer: any,
  data: any,
  selectedUnitId: string | null,
  availableMoves: any[],
  hoverHex: { q: number, r: number } | null
) {

  if (!layer || !data) return;

  layer.clear();

  // ✅ selected
  let selectedUnit = null;

  if (selectedUnitId) {
    selectedUnit = data.units?.find((u: any) => u.id === selectedUnitId);

    if (selectedUnit) {
      layer.drawSelected(selectedUnit.q, selectedUnit.r);
    }
  }

  // ✅ hover
  if (
    hoverHex &&
    availableMoves.some(m => m.q === hoverHex.q && m.r === hoverHex.r)
  ) {
    layer.drawHover(hoverHex.q, hoverHex.r);
  }

  // ✅ moves
  if (availableMoves.length > 0) {
    layer.drawMoves(availableMoves);
  }
}