import * as PIXI from "pixi.js";
import { axialToPixel, HEX_SIZE } from "./hexGridRenderer";
import { animateMove } from "../animation/animateMove";
import { drawArrowPixels } from "../animation/visuals";

export async function moveUnit(
  container: PIXI.Container,
  unitId: string,
  targetQ: number,
  targetR: number
): Promise<void> {
  // Find sprite
  const sprite = container.children.find(
    (c: any) => c.__unitId === unitId && c.__type === "unit"
  ) as PIXI.Container | undefined;

  if (!sprite) {
    console.warn("❌ moveUnit: sprite not found for", unitId);
    return;
  }

  // Calculate target position
  const { x, y } = axialToPixel(targetQ, targetR);
  const targetX = Math.round(x);
  const targetY = Math.round(y + HEX_SIZE);

  // Check if already at destination
  const dx = sprite.x - targetX;
  const dy = sprite.y - targetY;
  const dist = dx * dx + dy * dy;

  if (dist < 1) {
    return;
  }

  // Step 1: Draw arrow
  const fromPos = sprite.getGlobalPosition();
  const tempPoint = new PIXI.Point(targetX, targetY);
  const globalTargetPos = container.toGlobal(tempPoint);

  const stage = container.parent?.parent;
  const fxLayer = stage?.children?.find((c: any) => c.label === "fxLayer") || stage;

  if (fxLayer) {
    drawArrowPixels(
      fromPos.x,
      fromPos.y,
      globalTargetPos.x,
      globalTargetPos.y,
      fxLayer
    );
  }

  // Step 2: Animate movement (includes sound in animateMove)
  await new Promise<void>((resolve) => {
    animateMove(sprite, { x: targetX, y: targetY }, null, 380, resolve);
  });
}
