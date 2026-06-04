import * as PIXI from "pixi.js";
import { axialToPixel, HEX_SIZE } from "./hexGridRenderer";
import { initUnitLayerState, getSelectedUnitId, getHighlightedUnitId } from "./unitLayerState";
import { createUnitSprite } from "./unitLayerSprite";
import { updateHighlight } from "./unitLayerHighlight";
import { moveUnit } from "./unitLayerMovement";

export class UnitLayer {
  public container: PIXI.Container;
  private spritesById: Map<string, PIXI.Container>;
  private pendingCreateById: Map<string, Promise<PIXI.Container>>;

  constructor(world: PIXI.Container) {
    this.container = new PIXI.Container();
    this.container.label = "unitLayer";
    this.container.sortableChildren = true;
    this.spritesById = new Map();
    this.pendingCreateById = new Map();

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

    // Defensive cleanup for historical duplicate sprites:
    // keep only one unit sprite per __unitId.
    const keepFirst = new Set<string>();
    const duplicateSprites: PIXI.Container[] = [];
    this.container.children.forEach((child: any) => {
      if (child.__type !== "unit" || !child.__unitId) return;
      if (keepFirst.has(child.__unitId)) {
        duplicateSprites.push(child as PIXI.Container);
      } else {
        keepFirst.add(child.__unitId);
      }
    });
    duplicateSprites.forEach((child) => {
      this.container.removeChild(child);
      child.destroy({ children: true });
    });

    for (const unit of units) {
      const id = unit.id;

      // Get or create sprite
      let sprite = this.spritesById.get(id);
      if (sprite && sprite.parent !== this.container) {
        this.spritesById.delete(id);
        sprite = undefined;
      }

      if (!sprite) {
        let pending = this.pendingCreateById.get(id);
        if (!pending) {
          pending = createUnitSprite(unit);
          this.pendingCreateById.set(id, pending);
        }
        sprite = await pending;
        this.pendingCreateById.delete(id);

        const current = this.spritesById.get(id);
        if (current) {
          // Another sync already resolved and registered this unit.
          if (sprite !== current) {
            sprite.destroy({ children: true });
          }
          sprite = current;
        } else {
          this.spritesById.set(id, sprite);
          this.container.addChild(sprite);
        }
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
      sprite.visible = true;

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
      if (child.__type === "unit" && child.__unitId && !seen.has(child.__unitId)) {
        toRemove.push(child);
      }
    });

    toRemove.forEach((child) => {
      this.spritesById.delete((child as any).__unitId);
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
