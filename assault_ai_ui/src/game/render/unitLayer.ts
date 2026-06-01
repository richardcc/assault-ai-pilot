import * as PIXI from "pixi.js";
import { unitImages } from "../config/unitImages";
import { sides } from "../config/sides";
import { axialToPixel, HEX_SIZE } from "./hexGridRenderer";
import { updateUnitMovement } from "../systems/unitMovementSystem";

// --------------------------------------------------
// GLOBAL STATE (selection / hover)
// --------------------------------------------------
let highlightedUnitId: string | null = null;
let selectedUnitId: string | null = null;

(window as any).selectUnit = (id: string | null) => {
  selectedUnitId = id;
};

(window as any).highlightUnit = (id: string | null) => {
  highlightedUnitId = id;
};

// --------------------------------------------------
// HIGHLIGHTS CACHE
// --------------------------------------------------
const highlights = new Map<string, PIXI.Graphics>();

// --------------------------------------------------
// UNIT LAYER
// --------------------------------------------------
export class UnitLayer {
  public container: PIXI.Container;

  constructor(world: PIXI.Container) {
    this.container = new PIXI.Container();
    this.container.label = "unitLayer";
    this.container.sortableChildren = true;

    world.addChild(this.container);
  }

  // --------------------------------------------------
  // MAIN SYNC
  // --------------------------------------------------
  async sync(state: any) {
    if (!state) return;

    const units = state.units || [];
    const activeSide = state.active_side;
    const activated = state.activated_units || [];

    const seen = new Set<string>();

    for (const unit of units) {
      const id = unit.id;

      // ---------------------------------------------
      // GET / CREATE SPRITE
      // ---------------------------------------------
      let sprite = this.container.children.find(
        (c: any) =>
          c.__unitId === id &&
          c.__type === "unit"
      ) as PIXI.Container | undefined;

      if (!sprite) {
        sprite = await this.createSprite(unit);
        this.container.addChild(sprite);
      }

      // ---------------------------------------------
      // POSITION + MOVEMENT (EXTERNAL SYSTEM ✅)
      // ---------------------------------------------
      const { x, y } = axialToPixel(unit.q, unit.r);

      const newX = Math.round(x);
      const newY = Math.round(y + HEX_SIZE);

      updateUnitMovement(
        sprite,
        newX,
        newY,
        this.container
      );

      // ---------------------------------------------
      // VISUAL STATE
      // ---------------------------------------------
      const base = (sprite as any).__baseScale ?? 1;

      const isOwn = unit.side === activeSide;
      const isAvailable =
        isOwn &&
        !activated.includes(id) &&
        !(window as any).__hiddenHighlights?.has(id);

      sprite.scale.set(base);

      if (id === selectedUnitId) {
        sprite.scale.set(base * 1.3);
      } else if (id === highlightedUnitId) {
        sprite.scale.set(base * 1.2);
      }

      if (unit.hp <= 0) {
        sprite.alpha = 0.4;
      } else if (!isOwn || !isAvailable) {
        sprite.alpha = 0.7;
      } else {
        sprite.alpha = 1;
      }

      // ---------------------------------------------
      // HIGHLIGHTS
      // ---------------------------------------------
      this.updateHighlight(sprite, id, isAvailable);

      seen.add(id);
    }

    // ---------------------------------------------
    // CLEANUP
    // ---------------------------------------------
    this.container.children.forEach((child: any) => {
      if (child.__unitId && seen.has(child.__unitId)) {
        child.visible = true;
      }
    });
  }

  // --------------------------------------------------
  // HIGHLIGHT LOGIC
  // --------------------------------------------------
  private updateHighlight(sprite: any, id: string, isAvailable: boolean) {
    let highlight = highlights.get(id);

    if (isAvailable) {
      if (!highlight) {
        highlight = new PIXI.Graphics();

        (highlight as any).__type = "fx";
        (highlight as any).__unitId = id;

        highlight.circle(0, 0, HEX_SIZE * 0.8);
        highlight.fill({ color: 0x00ff00, alpha: 0.25 });

        highlight.zIndex = -1;
        highlight.eventMode = "none";

        this.container.addChild(highlight);
        highlights.set(id, highlight);
      }

      highlight.x = sprite.x;
      highlight.y = sprite.y;
      highlight.visible = true;

      highlight.alpha = 0.5 + Math.sin(Date.now() / 300) * 0.3;

    } else if (highlight) {
      this.container.removeChild(highlight);
      highlights.delete(id);
    }
  }

  // --------------------------------------------------
  // SPRITE CREATION
  // --------------------------------------------------
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

      const scale = (HEX_SIZE * 3) / texture.width;
      sprite.scale.set(scale);

      (container as any).__baseScale = scale;

      container.addChild(sprite);

    } catch (err) {
      console.error("❌ error loading sprite:", def.full, err);
    }

    this.addLabel(container, unit);
    this.addInteraction(container, unit);

    return container;
  }

  // --------------------------------------------------
  // LABEL
  // --------------------------------------------------
  private addLabel(container: PIXI.Container, unit: any) {
    const side = sides[unit.side] || { bgColor: 0x333333 };

    const labelContainer = new PIXI.Container();

    const bg = new PIXI.Graphics();
    bg.roundRect(-14, -7, 28, 14, 3);
    bg.fill({ color: side.bgColor, alpha: 0.85 });

    const label = new PIXI.Text({
      text: unit.id,
      style: {
        fontSize: 7,
        fill: "#ffffff"
      },
      resolution: 2,
    });

    label.anchor.set(0.5);
    label.roundPixels = true;

    labelContainer.addChild(bg);
    labelContainer.addChild(label);

    labelContainer.y = HEX_SIZE * 0.4;

    container.addChild(labelContainer);
  }

  // --------------------------------------------------
  // INTERACTION
  // --------------------------------------------------
  private addInteraction(container: PIXI.Container, unit: any) {
    container.eventMode = "static";

    container.on("pointerdown", () => {
      (window as any).onUnitClick?.(unit);
    });
  }
}