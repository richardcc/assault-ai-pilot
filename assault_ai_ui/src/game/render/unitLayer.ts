import * as PIXI from "pixi.js";
import { axialToPixel, HEX_SIZE } from "./hexGridRenderer";
import { initUnitLayerState, getSelectedUnitId, getHighlightedUnitId } from "./unitLayerState";
import { createUnitSprite } from "./unitLayerSprite";
import { updateHighlight } from "./unitLayerHighlight";
import { moveUnit } from "./unitLayerMovement";

export class UnitLayer {
  public container: PIXI.Container;

  constructor(world: PIXI.Container) {
    this.container = new PIXI.Container();
    this.container.label = "unitLayer";
    this.container.sortableChildren = true;

    world.addChild(this.container);
    initUnitLayerState();
  }

  /**
   * Synchronize unit layer with game state
   */
  async sync(state: any) {
    if (!state) return;

    const units = state.units || [];
    const activeSide = state.active_side;
    const activated = state.activated_units || [];
    const seen = new Set<string>();

    for (const unit of units) {
      const id = unit.id;

      // Get or create sprite
      let sprite = this.container.children.find(
        (c: any) => c.__unitId === id && c.__type === "unit"
      ) as PIXI.Container | undefined;

      if (!sprite) {
        sprite = await createUnitSprite(unit);
        this.container.addChild(sprite);
      }

      // Update position (no animation - snap if not moving)
      const { x, y } = axialToPixel(unit.q, unit.r);
      const newX = Math.round(x);
      const newY = Math.round(y + HEX_SIZE);

      const isMoving = sprite.__isMoving === true;
      if (!isMoving) {
        sprite.x = newX;
        sprite.y = newY;
      }

      // Update visual state
      const base = (sprite as any).__baseScale ?? 1;
      const isOwn = unit.side === activeSide;
      const isAvailable =
        isOwn &&
        !activated.includes(id) &&
        !(window as any).__hiddenHighlights?.has(id);

      sprite.scale.set(base);

      if (id === getSelectedUnitId()) {
        sprite.scale.set(base * 1.3);
      } else if (id === getHighlightedUnitId()) {
        sprite.scale.set(base * 1.2);
      }

      if (unit.hp <= 0) {
        sprite.visible = false;
        sprite.alpha = 0.4;
        seen.add(id);
        continue;
      }

      if (!isOwn || !isAvailable) {
        sprite.alpha = 0.7;
      } else {
        sprite.alpha = 1;
      }

      // Update highlight
      updateHighlight(this.container, sprite, id, isAvailable);

      seen.add(id);
    }

    // Cleanup stale sprites for units no longer present in state
    const toRemove: any[] = [];
    this.container.children.forEach((child: any) => {
      if (child.__unitId && !seen.has(child.__unitId)) {
        toRemove.push(child);
      }
    });

    toRemove.forEach((child) => {
      this.container.removeChild(child);
      child.destroy({ children: true });
    });
  }

  /**
   * Central movement manager for both human and AI
   * Handles: arrow, animation, and sound
   */
  public async moveUnit(
    unitId: string,
    targetQ: number,
    targetR: number
  ): Promise<void> {
    await moveUnit(this.container, unitId, targetQ, targetR);
  }
}
