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

      highlight.circle(0, 0, HEX_SIZE * 0.8);
      highlight.fill({ color: 0x00ff00, alpha: 0.25 });

      highlight.zIndex = -1;
      highlight.eventMode = "none";

      container.addChild(highlight);
      highlights.set(unitId, highlight);
    }

    highlight.x = sprite.x;
    highlight.y = sprite.y;
    highlight.visible = true;
    highlight.alpha = 0.5 + Math.sin(Date.now() / 300) * 0.3;
  } else if (highlight) {
    container.removeChild(highlight);
    highlights.delete(unitId);
  }
}
