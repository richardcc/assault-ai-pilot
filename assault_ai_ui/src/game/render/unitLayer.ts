import * as PIXI from "pixi.js";
import { unitImages } from "../config/unitImages";
import { sides } from "../config/sides";
import { axialToPixel, HEX_SIZE } from "./hexGridRenderer";

// ✅ hover global (viene del panel)
let highlightedUnitId: string | null = null;

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
  async sync(units: any[]) {
    const seen = new Set<string>();

    for (const unit of units) {
      let sprite = this.sprites[unit.id];

      if (!sprite) {
        this.createSprite(unit).then((s) => {
          this.sprites[unit.id] = s;
          this.container.addChild(s);
        });
        continue;
      }

      // ✅ posición EXACTA del hex
      const { x, y } = axialToPixel(unit.q, unit.r);

      sprite.x = Math.round(x);
      sprite.y = Math.round(y + HEX_SIZE);

      // ✅ escala base segura
      const base = (sprite as any).__baseScale ?? 1;

      // ✅ hover highlight
      if (unit.id === highlightedUnitId) {
        sprite.scale.set(base * 1.2);   // pequeño zoom
        sprite.alpha = 1;
      } else {
        sprite.scale.set(base);
        sprite.alpha = unit.hp <= 0 ? 0.4 : 1;
      }

      seen.add(unit.id);
    }

    // ✅ limpiar eliminados
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

      // ✅ guardar escala base (IMPORTANTE)
      (container as any).__baseScale = baseScale;

      container.addChild(sprite);
    } catch (err) {
      console.error("❌ error loading sprite:", def.full, err);
    }

    // ✅ config facción
    const side = sides[unit.side] || {
      bgColor: 0x333333,
    };

    // ✅ LABEL
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

    labelContainer.y = HEX_SIZE * 0.4; // ✅ bien centrado dentro del hex

    container.addChild(labelContainer);

    return container;
  }
}