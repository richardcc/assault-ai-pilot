import {
  HEX_R,
  HEX_ROW_STEP,
  HEX_W,
  COLS
} from "./grid.js";

/**
 * Terrain is scaled to match the FULL grid outline,
 * not just the hex centers.
 *
 * The grid outline extends HALF HEX_W to the left.
 */
export function drawTerrain(ctx, camera, mapS3, mapS2) {
  const zoom = camera.zoom;

  // ✅ REAL grid width (including left half-hex overhang)
  const worldWidth = COLS * HEX_W + HEX_W / 2;

  const rowsPerSection = 8;
  const sectionWorldHeight =
    (rowsPerSection - 1) * HEX_ROW_STEP + 2 * HEX_R;

  // Leftmost grid boundary is at -HEX_W/2
  const worldMinX = -HEX_W / 2;
  const screenX = (worldMinX - camera.x) * zoom;

  // ----------------------------
  // S3 (rows 0..7)
  // ----------------------------
  if (mapS3 && mapS3.complete) {
    const s3WorldY = -HEX_R;

    const scaleX = worldWidth / mapS3.width;
    const scaleY = sectionWorldHeight / mapS3.height;

    ctx.drawImage(
      mapS3,
      screenX,
      (s3WorldY - camera.y) * zoom,
      mapS3.width * scaleX * zoom,
      mapS3.height * scaleY * zoom
    );
  }

  // ----------------------------
  // S2 (rows 8..15)
  // ----------------------------
  if (mapS2 && mapS2.complete) {
    const s2WorldY =
      rowsPerSection * HEX_ROW_STEP - HEX_R;

    const scaleX = worldWidth / mapS2.width;
    const scaleY = sectionWorldHeight / mapS2.height;

    ctx.drawImage(
      mapS2,
      screenX,
      (s2WorldY - camera.y) * zoom,
      mapS2.width * scaleX * zoom,
      mapS2.height * scaleY * zoom
    );
  }
}