/**
 * Global state management for unit selection and highlighting
 */

let highlightedUnitId: string | null = null;
let selectedUnitId: string | null = null;

export function initUnitLayerState() {
  (window as any).selectUnit = (id: string | null) => {
    selectedUnitId = id;
  };

  (window as any).highlightUnit = (id: string | null) => {
    highlightedUnitId = id;
  };
}

export function getSelectedUnitId(): string | null {
  return selectedUnitId;
}

export function getHighlightedUnitId(): string | null {
  return highlightedUnitId;
}
