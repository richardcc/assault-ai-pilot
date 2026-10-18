import * as PIXI from "pixi.js";
import { unitImages } from "../config/unitImages";
import { sides } from "../config/sides";
import { HEX_SIZE } from "./hexGridRenderer";
import { actionMarkerImages, getUnitActionMarker } from "../state/actionMarkers";

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
  await updateUnitActionMarker(container, unit.id);
  updateUnitTacticalIndicators(container, unit);
  addUnitInteraction(container, unit);

  return container;
}

export async function updateUnitActionMarker(container: PIXI.Container, unitId: string): Promise<void> {
  if (!container || (container as any).destroyed) return;
  const marker = getUnitActionMarker(unitId);
  const existing = container.getChildByName("action-marker") as PIXI.Sprite | null;
  if (!marker) {
    if (existing && !existing.destroyed) {
      container.removeChild(existing);
      existing.destroy();
    }
    return;
  }

  const markerPath = actionMarkerImages[marker];
  if (!markerPath) return;

  try {
    const texture = await PIXI.Assets.load(markerPath);
    if (!container || (container as any).destroyed) return;

    let sprite = container.getChildByName("action-marker") as PIXI.Sprite | null;
    if (!sprite || sprite.destroyed) {
      sprite = new PIXI.Sprite(texture);
      sprite.name = "action-marker";
      sprite.anchor.set(0.5);
      sprite.zIndex = 50;
      container.addChild(sprite);
    } else {
      sprite.texture = texture;
    }

    if (texture && texture.width > 0) {
      const scale = 20 / texture.width;
      sprite.scale.set(scale);
    } else {
      sprite.width = 20;
      sprite.height = 20;
    }
    sprite.x = HEX_SIZE * 0.5;
    sprite.y = -HEX_SIZE * 0.55;
    sprite.alpha = 0.95;
  } catch (err) {
    console.error("❌ Error loading action marker:", markerPath, err);
  }
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

export function updateUnitTacticalIndicators(container: PIXI.Container, unit: any) {
  if (!container || !unit) return;

  // 1. Health Pip Bar
  const healthBarName = "unit-health-bar";
  let healthBar = container.getChildByName(healthBarName) as PIXI.Graphics | null;
  if (!healthBar) {
    healthBar = new PIXI.Graphics();
    healthBar.name = healthBarName;
    healthBar.zIndex = 60;
    container.addChild(healthBar);
  }

  healthBar.clear();
  const maxHp = Math.max(1, Number(unit.max_hp || 2));
  const hp = Math.max(0, Number(unit.hp != null ? unit.hp : maxHp));
  const pct = Math.min(1, Math.max(0, hp / maxHp));

  const barW = 24;
  const barH = 3.5;
  const barX = -barW / 2;
  const barY = -HEX_SIZE * 0.48;

  // Background box
  healthBar.roundRect(barX - 0.5, barY - 0.5, barW + 1, barH + 1, 1.5);
  healthBar.fill({ color: 0x050810, alpha: 0.85 });
  healthBar.stroke({ width: 0.8, color: 0x334155, alpha: 0.9 });

  // Health fill
  const fillColor = pct > 0.6 ? 0x22c55e : (pct > 0.3 ? 0xeab308 : 0xef4444);
  const fillW = Math.max(0, (barW - 1) * pct);
  if (fillW > 0) {
    healthBar.roundRect(barX + 0.5, barY + 0.5, fillW, barH - 1, 1);
    healthBar.fill({ color: fillColor, alpha: 0.95 });
  }

  // Pip dividers
  if (maxHp > 1) {
    const step = (barW - 1) / maxHp;
    for (let i = 1; i < maxHp; i++) {
      const pipX = barX + 0.5 + i * step;
      healthBar.moveTo(pipX, barY);
      healthBar.lineTo(pipX, barY + barH);
      healthBar.stroke({ width: 0.6, color: 0x000000, alpha: 0.7 });
    }
  }

  // 2. Role Badge (M for mortar, MG for HMG, A for assault)
  const roleBadgeName = "unit-role-badge";
  let roleBadge = container.getChildByName(roleBadgeName) as PIXI.Container | null;

  const role = unit.tactical_role;
  const badgeConfig = unit.has_indirect_fire || role === "indirect_mortar"
    ? { text: "M", bg: 0x7c3aed, border: 0xa855f7 }
    : unit.is_suppression_mg || role === "suppression_mg"
    ? { text: "MG", bg: 0xd97706, border: 0xfbbf24 }
    : unit.is_assault_squad || role === "assault_squad"
    ? { text: "A", bg: 0xdc2626, border: 0xf87171 }
    : null;

  if (!badgeConfig) {
    if (roleBadge) {
      container.removeChild(roleBadge);
      roleBadge.destroy({ children: true });
    }
    return;
  }

  if (!roleBadge) {
    roleBadge = new PIXI.Container();
    roleBadge.name = roleBadgeName;
    roleBadge.zIndex = 65;
    container.addChild(roleBadge);
  } else {
    roleBadge.removeChildren();
  }

  const badgeX = -HEX_SIZE * 0.46;
  const badgeY = HEX_SIZE * 0.38;

  const bg = new PIXI.Graphics();
  bg.circle(badgeX, badgeY, 6.5);
  bg.fill({ color: badgeConfig.bg, alpha: 0.92 });
  bg.stroke({ width: 1.2, color: badgeConfig.border, alpha: 1.0 });

  const text = new PIXI.Text({
    text: badgeConfig.text,
    style: {
      fontSize: 6,
      fontWeight: "bold",
      fill: "#ffffff",
      align: "center",
    },
    resolution: 2,
  });
  text.anchor.set(0.5);
  text.x = badgeX;
  text.y = badgeY;

  roleBadge.addChild(bg);
  roleBadge.addChild(text);
}
