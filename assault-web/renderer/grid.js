// renderer/grid.js

export const HEX_R = 52;
export const HEX_W = Math.sqrt(3) * HEX_R;
export const HEX_ROW_STEP = 1.5 * HEX_R;

export const COLS = 9;
export const TOTAL_ROWS = 16;

/**
 * Centro del hex en coordenadas de MUNDO.
 * ESTA FUNCIÓN ES LA FUENTE DE VERDAD DEL SISTEMA.
 */
export function hexToWorld(col, row) {
  const x = col * HEX_W + (row % 2) * (HEX_W / 2);
  const y = row * HEX_ROW_STEP;
  return { x, y };
}