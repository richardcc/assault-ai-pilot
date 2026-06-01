import { animateMove } from "../animation/animateMove";
import { drawArrowPixels } from "../animation/visuals";

export function updateUnitMovement(
  sprite: any,
  newX: number,
  newY: number,
  unitLayer: any
) {
  const isMoving = sprite.__isMoving === true;

  const dx = sprite.x - newX;
  const dy = sprite.y - newY;
  const dist = dx * dx + dy * dy;

  if (isMoving && dist < 1) {
    sprite.__isMoving = false;
  }

  if (dist > 1 && !isMoving) {

    // ✅ obtener posición global REAL
    const from = sprite.getGlobalPosition();

    // ✅ obtener stage
    const stage = unitLayer.parent.parent; // world → stage

    // ✅ dibujar en stage (igual que tu FX layer manual)
    drawArrowPixels(
      from.x,
      from.y,
      newX,
      newY,
      stage
    );

    animateMove(sprite, { x: newX, y: newY }, null);
  }
  else if (!isMoving && dist < 1) {
    sprite.x = newX;
    sprite.y = newY;
  }
}
