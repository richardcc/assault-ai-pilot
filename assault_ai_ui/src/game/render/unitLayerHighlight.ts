import * as PIXI from "pixi.js";
import { HEX_SIZE } from "./hexGridRenderer";

const highlights = new Map<string, PIXI.Graphics>();

export function updateHighlight(
  container: PIXI.Container,
  sprite: any,
  unitId: string,
  isAvailable: boolean
) {
  let highlight = highlights.get(unitId);

  if (isAvailable) {
    if (!highlight) {
      highlight = new PIXI.Graphics();
      (highlight as any).__type = "fx";
      (highlight as any).__unitId = unitId;

      // Outer tactical ready ring wrapping clearly around unit counter
      highlight.circle(0, 0, HEX_SIZE * 0.92);
      highlight.stroke({ width: 2.4, color: 0x00f0ff, alpha: 0.9 });
      highlight.fill({ color: 0x00f0ff, alpha: 0.12 });

      // Glowing corner pips
      highlight.circle(0, -HEX_SIZE * 0.92, 2.5);
      highlight.fill({ color: 0x00ff88, alpha: 1.0 });

      highlight.zIndex = 30;
      highlight.eventMode = "none";

      container.addChild(highlight);
      highlights.set(unitId, highlight);
    }

    highlight.x = sprite.x;
    highlight.y = sprite.y;
    highlight.visible = true;
    highlight.alpha = 0.7 + Math.sin(Date.now() / 250) * 0.3;
  } else if (highlight) {
    container.removeChild(highlight);
    highlights.delete(unitId);
  }
}
