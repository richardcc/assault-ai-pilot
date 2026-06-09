import * as PIXI from "pixi.js";
import { unitImages } from "../config/unitImages";
import { sides } from "../config/sides";
import { HEX_SIZE } from "./hexGridRenderer";

export async function createUnitSprite(unit: any): Promise<PIXI.Container> {
  const container = new PIXI.Container();

  (container as any).__unitId = unit.id;
  (container as any).__isMoving = false;
  (container as any).__type = "unit";

  const unitKey = unit.unit_key || unit.type;
  const def = unitImages[unitKey as keyof typeof unitImages];

  if (!def) {
    console.warn("❌ Missing sprite for", unitKey);
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
    console.error("❌ Error loading sprite:", def.full, err);
  }

  addUnitLabel(container, unit);
  addUnitInteraction(container, unit);

  return container;
}

function addUnitLabel(container: PIXI.Container, unit: any) {
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

function addUnitInteraction(container: PIXI.Container, unit: any) {
  container.eventMode = "static";
  container.on("pointerdown", () => {
    (window as any).onUnitClick?.(unit);
  });
}
