import * as PIXI from "pixi.js";
import { unitImages } from "../config/unitImages";
import { sides } from "../config/sides";
import { axialToPixel, HEX_SIZE } from "./hexGridRenderer";

// ✅ global hover / selection
let highlightedUnitId: string | null = null;
let selectedUnitId: string | null = null;

// ✅ highlights separados
const highlights = new Map<string, PIXI.Graphics>();

(window as any).selectUnit = (id: string | null) => {
  selectedUnitId = id;
};

(window as any).highlightUnit = (id: string | null) => {
  highlightedUnitId = id;
};

export class UnitLayer {
  public container: PIXI.Container;

  constructor(world: PIXI.Container) {
    this.container = new PIXI.Container();
    this.container.label = "unitLayer";

    // ✅ importante para layering correcto
    this.container.sortableChildren = true;

    world.addChild(this.container);
  }

  async sync(state: any) {
    if (!state) return;

    const units = state.units || [];
    const activeSide = state.active_side;
    const activated = state.activated_units || [];

    const seen = new Set<string>();

    for (const unit of units) {
      const id = unit.id;

      let sprite = this.container.children.find(
        (c: any) =>
          c.__unitId === id &&
          c.__type === "unit"
      ) as PIXI.Container | undefined;

      if (!sprite) {
        sprite = await this.createSprite(unit);
        this.container.addChild(sprite);
      }

      // ✅ posición
      const { x, y } = axialToPixel(unit.q, unit.r);

      const newX = Math.round(x);
      const newY = Math.round(y + HEX_SIZE);

      const isMoving = (sprite as any).__isMoving === true;

      const dx = sprite.x - newX;
      const dy = sprite.y - newY;
      const dist = dx * dx + dy * dy;

      // If flagged as moving but already at destination — release the lock
      if (isMoving && dist < 1) {
        (sprite as any).__isMoving = false;
      }

      if (!isMoving || dist < 1) {
        sprite.x = newX;
        sprite.y = newY;
      }

      const base = (sprite as any).__baseScale ?? 1;

      const isOwn = unit.side === activeSide;
      const isAvailable =
        isOwn &&
        !activated.includes(id) &&
        !(window as any).__hiddenHighlights?.has(id);

      // 💣 ✅ FIX REAL DEL BUG: reset FORZADO
      sprite.scale.x = base;
      sprite.scale.y = base;

      // ✅ aplicar estados
      if (id === selectedUnitId) {
        sprite.scale.x = base * 1.3;
        sprite.scale.y = base * 1.3;
      } else if (id === highlightedUnitId) {
        sprite.scale.x = base * 1.2;
        sprite.scale.y = base * 1.2;
      }

      // ✅ alpha
      if (unit.hp <= 0) {
        sprite.alpha = 0.4;
      } else if (!isOwn || !isAvailable) {
        sprite.alpha = 0.7;
      } else {
        sprite.alpha = 1;
      }

      // -----------------------------------------
      // ✅ highlight separado (correcto)
      let highlight = highlights.get(id);

      if (isAvailable) {

        if (!highlight) {
          highlight = new PIXI.Graphics();

          (highlight as any).__type = "fx";
          (highlight as any).__unitId = id;
          (highlight as any).name = "availableHighlight";

          // ✅ Pixi v8 API correcta
          highlight.circle(0, 0, HEX_SIZE * 0.8);
          highlight.fill({ color: 0x00ff00, alpha: 0.25 });

          highlight.zIndex = -1;
          highlight.eventMode = "none";

          this.container.addChild(highlight);
          highlights.set(id, highlight);
        }

        // ✅ seguir al sprite
        highlight.x = sprite.x;
        highlight.y = sprite.y;
        highlight.visible = true;

        highlight.alpha = 0.5 + Math.sin(Date.now() / 300) * 0.3;

      } else {
        if (highlight) {
          this.container.removeChild(highlight);
          highlights.delete(id);
        }
      }

      seen.add(id);
    }

    // ✅ mantener visibles
    this.container.children.forEach((child: any) => {
      if (child.__unitId && seen.has(child.__unitId)) {
        child.visible = true;
      }
    });
  }

  // -----------------------------------------
  private async createSprite(unit: any): Promise<PIXI.Container> {
    const container = new PIXI.Container();

    (container as any).__unitId = unit.id;
    (container as any).__isMoving = false;
    (container as any).__type = "unit";

    const def = unitImages[unit.unit_key];

    if (!def) {
      console.warn("❌ missing sprite for", unit.unit_key);
      return container;
    }

    try {
      const texture = await PIXI.Assets.load(def.full);

      const sprite = new PIXI.Sprite(texture);
      sprite.anchor.set(0.5);

      const desiredSize = HEX_SIZE * 3;
      const baseScale = desiredSize / texture.width;

      sprite.scale.set(baseScale);

      (container as any).__baseScale = baseScale;

      container.addChild(sprite);

    } catch (err) {
      console.error("❌ error loading sprite:", def.full, err);
    }

    // ✅ etiqueta
    const side = sides[unit.side] || { bgColor: 0x333333 };

    const labelContainer = new PIXI.Container();

    const bg = new PIXI.Graphics();
    bg.roundRect(-14, -7, 28, 14, 3);
    bg.fill({ color: side.bgColor, alpha: 0.85 });

    labelContainer.addChild(bg);

    const label = new PIXI.Text({
      text: unit.id,
      style: {
        fontSize: 7,
        fill: "#ffffff",
      },
      resolution: 2,
    });

    label.anchor.set(0.5);
    label.roundPixels = true;

    labelContainer.addChild(label);
    labelContainer.y = HEX_SIZE * 0.4;

    container.addChild(labelContainer);

    container.eventMode = "static";

    container.on("pointerdown", () => {
      if ((window as any).onUnitClick) {
        (window as any).onUnitClick(unit);
      }
    });

    return container;
  }
}
