import * as PIXI from "pixi.js";
import { axialToPixel, HEX_SIZE } from "../render/hexGridRenderer";

// --------------------------------------------------
// CACHE (NO SPAM AL BACKEND)
// --------------------------------------------------
let lastHexKey = "";
let cachedTargeting: any = null;
let targetingRequestSeq = 0;


// --------------------------------------------------
// CREATE
// --------------------------------------------------
export function createDebugVector(app: PIXI.Application) {

  const graphics = new PIXI.Graphics();

  const text = new PIXI.Text("", {
    fill: "#ff0000",
    fontSize: 16
  });

  // Container for dice sprites (same art as the combat panel)
  const diceContainer = new PIXI.Container();

  app.stage.addChild(graphics);
  app.stage.addChild(diceContainer);
  app.stage.addChild(text);

  // Preload dice textures so sprites don't render as empty/gray squares
  preloadDiceTextures();

  return { graphics, text, diceContainer };
}


// --------------------------------------------------
// UPDATE
// --------------------------------------------------
export async function updateDebugVector({
  world,
  selectedUnitId,
  state,
  closestHex,
  event,
  debug
}: any) {

  if (!debug) return;

  // ✅ solo cuando CTRL está pulsado
  if (!event.originalEvent?.ctrlKey) {
    debug.graphics.clear();
    debug.text.text = "";
    clearDiceContainer(debug.diceContainer);
    return;
  }

  if (!selectedUnitId || !state?.units || !closestHex) {
    debug.graphics.clear();
    debug.text.text = "";
    clearDiceContainer(debug.diceContainer);
    return;
  }

  const unit = state.units.find((u: any) => u.id === selectedUnitId);
  if (!unit) return;

  const start = axialToPixel(unit.q, unit.r);
  const end = axialToPixel(closestHex.q, closestHex.r);

  const p1 = world.toGlobal({ x: start.x, y: start.y + HEX_SIZE });
  const p2 = world.toGlobal({ x: end.x, y: end.y + HEX_SIZE });

  const sx = p1.x;
  const sy = p1.y;
  const ex = p2.x;
  const ey = p2.y;

  const g = debug.graphics;
  g.clear();

  // --------------------------------------------------
  // ✅ BACKEND QUERY (LOS + DISTANCE REAL + PATH)
  // --------------------------------------------------
  const hexKey = `${selectedUnitId}_${closestHex.q}_${closestHex.r}`;

  const attackerId = unit.unit_id ?? unit.id ?? selectedUnitId;
  if (hexKey !== lastHexKey) {
    lastHexKey = hexKey;
    // Drop stale payload immediately so UI never shows previous
    // target's distance/LOS while a new request is in flight.
    cachedTargeting = null;
    const reqSeq = ++targetingRequestSeq;

    try {
      const res = await fetch(
        `http://127.0.0.1:8000/targeting?attacker_id=${attackerId}&q=${closestHex.q}&r=${closestHex.r}`
      );
      const payload = await res.json();
      // Ignore out-of-order responses from older requests.
      if (reqSeq !== targetingRequestSeq) return;
      if (!res.ok) {
        cachedTargeting = null;
      } else if (
        payload
        && typeof payload.distance === "number"
        && typeof payload.los === "string"
      ) {
        cachedTargeting = payload;
      } else {
        cachedTargeting = null;
      }

    } catch (e) {
      // Ignore out-of-order failures as well.
      if (reqSeq === targetingRequestSeq) {
        cachedTargeting = null;
      }
    }
  }

  const dist = cachedTargeting?.distance ?? "?";
  const los = cachedTargeting?.los ?? "UNKNOWN";
  const pathFull: [number, number][] =
    cachedTargeting?.path_full ?? cachedTargeting?.path ?? [];
  const blocking = cachedTargeting?.blocking ?? [];
  const hindrance = cachedTargeting?.hindrance ?? [];
  const dice = cachedTargeting?.dice ?? null;

  // --------------------------------------------------
  // ✅ COLOR SEGÚN LOS (el fuego indirecto ignora el LOS)
  // --------------------------------------------------
  const isIndirect = dice?.indirect === true;
  let color = 0xff0000;

  if (isIndirect) color = 0x00ccff;
  else if (los === "CLEAR") color = 0x00ff00;
  else if (los === "HINDERED") color = 0xffaa00;
  else if (los === "BLOCKED") color = 0xff0000;

  // --------------------------------------------------
  // ✅ FLECHA RECTA (centro a centro; el rayo no es polilínea)
  // --------------------------------------------------
  const dx = ex - sx;
  const dy = ey - sy;
  const length = Math.sqrt(dx * dx + dy * dy);

  if (length === 0) return;

  const nx = dx / length;
  const ny = dy / length;
  const mx = (sx + ex) / 2;
  const my = (sy + ey) / 2;
  const gap = 40;
  const gapStartX = mx - nx * gap;
  const gapStartY = my - ny * gap;
  const gapEndX = mx + nx * gap;
  const gapEndY = my + ny * gap;

  g.moveTo(sx, sy);
  g.lineTo(gapStartX, gapStartY);
  g.stroke({ width: 4, color });

  g.moveTo(gapEndX, gapEndY);
  g.lineTo(ex, ey);
  g.stroke({ width: 4, color });

  const angle = Math.atan2(ey - gapEndY, ex - gapEndX);
  const arrowSize = 18;

  g.moveTo(ex, ey);
  g.lineTo(
    ex - arrowSize * Math.cos(angle - Math.PI / 5),
    ey - arrowSize * Math.sin(angle - Math.PI / 5)
  );
  g.stroke({ width: 4, color });

  g.moveTo(ex, ey);
  g.lineTo(
    ex - arrowSize * Math.cos(angle + Math.PI / 5),
    ey - arrowSize * Math.sin(angle + Math.PI / 5)
  );
  g.stroke({ width: 4, color });

  // --------------------------------------------------
  // ✅ TODOS los hexes del rayo (🟣), bloqueados o no
  // --------------------------------------------------
  for (let i = 0; i < pathFull.length; i++) {
    const [q, r] = pathFull[i];
    const pos = axialToPixel(q, r);
    const p = world.toGlobal({ x: pos.x, y: pos.y + HEX_SIZE });

    g.circle(p.x, p.y, 8);
    g.fill({ color: 0xaa00ff, alpha: 0.55 });
  }

  for (const [q, r] of hindrance) {
    const pos = axialToPixel(q, r);
    const p = world.toGlobal({ x: pos.x, y: pos.y + HEX_SIZE });
    g.circle(p.x, p.y, 10);
    g.stroke({ width: 3, color: 0xffff00 });
  }

  for (const [q, r] of blocking) {
    const pos = axialToPixel(q, r);
    const p = world.toGlobal({ x: pos.x, y: pos.y + HEX_SIZE });
    g.circle(p.x, p.y, 12);
    g.stroke({ width: 4, color: 0xff0000 });
  }


  // --------------------------------------------------
  // ✅ TEXTO (distancia + LOS)
  // --------------------------------------------------
  debug.text.style.align = "center";
  debug.text.text = isIndirect
    ? `d=${dist} | INDIRECTO (ignora LOS)`
    : `d=${dist} | LOS=${los}`;
  debug.text.x = mx - debug.text.width / 2;
  debug.text.y = my - debug.text.height / 2 - (dice ? 34 : 0);

  // --------------------------------------------------
  // ✅ DADOS (imágenes, base → con modificadores)
  // --------------------------------------------------
  const diceContainer: PIXI.Container = debug.diceContainer;
  clearDiceContainer(diceContainer);

  if (dice) {
    const rowGap = 26;
    const baseY = my + 2;

    buildDiceRow(
      diceContainer,
      `ATK${dice.suppressed ? " (supr)" : ""}`,
      dice.attack,
      mx,
      baseY,
    );
    buildDiceRow(
      diceContainer,
      `DEF${dice.hindered ? " (hind)" : ""}`,
      dice.defense,
      mx,
      baseY + rowGap,
    );
  }
}

// --------------------------------------------------
// Dice sprite helpers (same art as the combat panel)
// --------------------------------------------------
const DIE_BASE_SRC: Record<string, string> = {
  RED: "/assets/dice/red_02.png",
  YELLOW: "/assets/dice/yellow_01.png",
  GREEN: "/assets/dice/green_01.png",
  BLUE: "/assets/dice/blue_01.png",
};

const DIE_SIZE = 22;
const DIE_SPACING = 3;
const _textureCache: Record<string, PIXI.Texture> = {};
let _dicePreloadStarted = false;

async function preloadDiceTextures() {
  if (_dicePreloadStarted) return;
  _dicePreloadStarted = true;

  await Promise.all(
    Object.values(DIE_BASE_SRC).map(async (src) => {
      try {
        const tex = await PIXI.Assets.load(src);
        _textureCache[src] = tex;
      } catch (e) {
        console.warn("[debugVector] failed to load die texture", src, e);
      }
    })
  );
}

function getDieTexture(color: string): PIXI.Texture | null {
  const src = DIE_BASE_SRC[color];
  if (!src) return null;
  return _textureCache[src] ?? null;
}

function clearDiceContainer(container: PIXI.Container | undefined) {
  if (!container) return;
  const children = [...container.children];
  for (const child of children) {
    container.removeChild(child);
    // Keep shared textures alive; only destroy the display object
    (child as any).destroy?.({ children: true, texture: false });
  }
}

function makeLabel(textValue: string): PIXI.Text {
  return new PIXI.Text(textValue, {
    fill: "#ffffff",
    fontSize: 13,
    fontWeight: "bold",
  });
}

function makeCaption(textValue: string): PIXI.Text {
  return new PIXI.Text(textValue, {
    fill: "#cccccc",
    fontSize: 10,
    fontStyle: "italic",
  });
}

type DieMark = "none" | "added" | "removed";

function makeDieCell(color: string, mark: DieMark = "none"): PIXI.Container {
  const cell = new PIXI.Container();

  const tex = getDieTexture(color);
  const sprite = new PIXI.Sprite(tex ?? PIXI.Texture.EMPTY);
  sprite.width = DIE_SIZE;
  sprite.height = DIE_SIZE;
  cell.addChild(sprite);

  // Texture not cached yet → load it and assign once ready
  if (!tex) {
    const src = DIE_BASE_SRC[color];
    if (src) {
      PIXI.Assets.load(src)
        .then((loaded: PIXI.Texture) => {
          _textureCache[src] = loaded;
          if (!(sprite as any).destroyed) {
            sprite.texture = loaded;
            sprite.width = DIE_SIZE;
            sprite.height = DIE_SIZE;
          }
        })
        .catch(() => {});
    }
  }

  // Highlight dice changed by modifiers
  if (mark === "added") {
    const border = new PIXI.Graphics();
    border.roundRect(-2, -2, DIE_SIZE + 4, DIE_SIZE + 4, 4);
    border.stroke({ width: 2.5, color: 0x00ff66 });
    cell.addChild(border);
  } else if (mark === "removed") {
    sprite.alpha = 0.3;
    const border = new PIXI.Graphics();
    border.roundRect(-2, -2, DIE_SIZE + 4, DIE_SIZE + 4, 4);
    border.stroke({ width: 2.5, color: 0xff3333 });
    // diagonal strike to signal removal
    border.moveTo(0, DIE_SIZE);
    border.lineTo(DIE_SIZE, 0);
    border.stroke({ width: 2, color: 0xff3333 });
    cell.addChild(border);
  }

  return cell;
}

function countByColor(arr: string[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const c of arr) out[c] = (out[c] ?? 0) + 1;
  return out;
}

/**
 * Lay out one row centered at (centerX, centerY):
 *   LABEL  base [dice]   →   final [dice]
 * - When modifiers change the pool, both groups are shown with "base"/"final"
 *   captions; added dice get a green border, removed dice a red strike.
 * - When nothing changes, only a single (unlabeled) pool is shown.
 */
function buildDiceRow(
  container: PIXI.Container,
  label: string,
  pair: { base?: string[]; modified?: string[] } | undefined,
  centerX: number,
  centerY: number,
) {
  if (!pair) return;

  const base = pair.base ?? [];
  const modified = pair.modified ?? [];
  const changed = base.join(",") !== modified.join(",");

  const baseCounts = countByColor(base);
  const modCounts = countByColor(modified);

  type Item = { obj: PIXI.Container; w: number };
  const items: Item[] = [];

  const pushObj = (obj: PIXI.Container, pad: number) =>
    items.push({ obj, w: (obj.width || 0) + pad });

  const pushCaption = (txt: string) => pushObj(makeCaption(txt), 4);
  const pushDie = (color: string, mark: DieMark) =>
    items.push({ obj: makeDieCell(color, mark), w: DIE_SIZE + DIE_SPACING });

  // Row label (ATK / DEF ...)
  pushObj(makeLabel(label), 8);

  if (!changed) {
    if (base.length === 0) pushObj(makeLabel("-"), 6);
    else base.forEach((c) => pushDie(c, "none"));
  } else {
    // ---- base group (mark removed dice) ----
    pushCaption("base");
    if (base.length === 0) {
      pushObj(makeLabel("-"), 6);
    } else {
      const removedLeft = { ...baseCounts };
      for (const c of Object.keys(removedLeft)) {
        removedLeft[c] = Math.max(0, baseCounts[c] - (modCounts[c] ?? 0));
      }
      base.forEach((c) => {
        let mark: DieMark = "none";
        if (removedLeft[c] > 0) {
          mark = "removed";
          removedLeft[c] -= 1;
        }
        pushDie(c, mark);
      });
    }

    // ---- arrow ----
    pushObj(makeLabel("→"), 8);

    // ---- final group (mark added dice) ----
    pushCaption("final");
    if (modified.length === 0) {
      pushObj(makeLabel("-"), 6);
    } else {
      const addedLeft = { ...modCounts };
      for (const c of Object.keys(addedLeft)) {
        addedLeft[c] = Math.max(0, modCounts[c] - (baseCounts[c] ?? 0));
      }
      modified.forEach((c) => {
        let mark: DieMark = "none";
        if (addedLeft[c] > 0) {
          mark = "added";
          addedLeft[c] -= 1;
        }
        pushDie(c, mark);
      });
    }
  }

  const totalW = items.reduce((sum, it) => sum + it.w, 0);
  let x = centerX - totalW / 2;

  for (const it of items) {
    const h = (it.obj as any).height ?? DIE_SIZE;
    it.obj.x = x;
    it.obj.y = centerY - h / 2;
    container.addChild(it.obj);
    x += it.w;
  }
}