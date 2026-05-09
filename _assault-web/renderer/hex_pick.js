// renderer/hex_pick.js

import { HEX_W, HEX_ROW_STEP } from "./grid.js";

export function worldToHex(worldX, worldY) {
  const row = Math.round(worldY / HEX_ROW_STEP);
  const col = Math.round(
    (worldX - (row % 2) * (HEX_W / 2)) / HEX_W
  );

  return { col, row };
}