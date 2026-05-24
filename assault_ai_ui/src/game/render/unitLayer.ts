import * as PIXI from "pixi.js";
import { unitImages } from "../config/unitImages";
import { sides } from "../config/sides";
import { axialToPixel, HEX_SIZE } from "./hexGridRenderer";

// ✅ hover global (viene del panel)
let highlightedUnitId: string | null = null;
let selectedUnitId: string | null = null;

(window as any).selectUnit = (id: string | null) => {
  selectedUnitId = id;
};

  
(window as any).highlightUnit = (id: string | null) => {
  highlightedUnitId = id;
};

export class UnitLayer {
  private container: PIXI.Container;
  private sprites: Record<string, PIXI.Container> = {};

  constructor(world: PIXI.Container) {
    this.container = new PIXI.Container();
    this.container.label = "unitLayer";
    world.addChild(this.container);
  }

  // -----------------------------------------
  async sync(state: any) {
    if (!state) return;

    const units = state.units || [];
    const activeSide = state.active_side;
    const activated = state.activated_units || [];

    const seen = new Set<string>();

    for (const unit of units) {

      let sprite = this.sprites[unit.id];

      // ✅ CREATE if missing
      if (!sprite) {
        sprite = await this.createSprite(unit);

        this.sprites[unit.id] = sprite;
        this.container.addChild(sprite);
      }

      // ✅ POSICIÓN
      const { x, y } = axialToPixel(unit.q, unit.r);

      sprite.x = Math.round(x);
      sprite.y = Math.round(y + HEX_SIZE);

      const base = (sprite as any).__baseScale ?? 1;

      // -----------------------------------------
      // ✅ ESTADOS
      const isOwn = unit.side === activeSide;
      const isAvailable = isOwn && !activated.includes(unit.id);

      if (unit.id === selectedUnitId) {
        sprite.scale.set(base * 1.3);
        sprite.tint = 0xffcc00; // 🟡 selección
      } else if (unit.id === highlightedUnitId) {
        sprite.scale.set(base * 1.2);
      } else {
        sprite.scale.set(base);
        sprite.tint = isOwn ? 0xffffff : 0xaaaaaa;
      }

      // ✅ alpha base
      if (unit.hp <= 0) {
        sprite.alpha = 0.4;
      } else if (!isOwn) {
        sprite.alpha = 0.7; // enemigo
      } else if (!isAvailable) {
        sprite.alpha = 0.7; // usada
      } else {
        sprite.alpha = 1; // disponible
      }

      // ✅ tint (opcional suave)
      sprite.tint = isOwn ? 0xffffff : 0xaaaaaa;

      // ✅ HIGHLIGHT DISPONIBLE (HALO)
      let highlight = sprite.getChildByName("availableHighlight");

      if (isAvailable) {
        if (!highlight) {
          highlight = new PIXI.Graphics();
          highlight.name = "availableHighlight";

          highlight.beginFill(0x00ff00, 0.25);
          highlight.drawCircle(0, 0, HEX_SIZE * 0.8);
          highlight.endFill();

          sprite.addChildAt(highlight, 0);
        }

        // ✅ animación suave
        highlight.alpha = 0.5 + Math.sin(Date.now() / 300) * 0.3;

      } else {
        if (highlight) {
          sprite.removeChild(highlight);
        }
      }

      seen.add(unit.id);
    }

    // ✅ cleanup
    Object.keys(this.sprites).forEach((id) => {
      if (!seen.has(id)) {
        this.container.removeChild(this.sprites[id]);
        this.sprites[id].destroy();
        delete this.sprites[id];
      }
    });
  }

  // -----------------------------------------
  private async createSprite(unit: any): Promise<PIXI.Container> {
    const container = new PIXI.Container();

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

    const side = sides[unit.side] || {
      bgColor: 0x333333,
    };

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