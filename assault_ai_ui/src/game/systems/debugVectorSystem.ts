import * as PIXI from "pixi.js";
import { axialToPixel, HEX_SIZE } from "../render/hexGridRenderer";

// --------------------------------------------------
// CACHE (NO SPAM AL BACKEND)
// --------------------------------------------------
let lastHexKey = "";
let cachedTargeting: any = null;


// --------------------------------------------------
// CREATE
// --------------------------------------------------
export function createDebugVector(app: PIXI.Application) {

  const graphics = new PIXI.Graphics();

  const text = new PIXI.Text("", {
    fill: "#ff0000",
    fontSize: 16
  });

  app.stage.addChild(graphics);
  app.stage.addChild(text);

  return { graphics, text };
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
    return;
  }

  if (!selectedUnitId || !state?.units || !closestHex) {
    debug.graphics.clear();
    debug.text.text = "";
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

  if (hexKey !== lastHexKey) {
    lastHexKey = hexKey;

    try {
      const res = await fetch(
        `http://127.0.0.1:8000/targeting?attacker_id=${selectedUnitId}&q=${closestHex.q}&r=${closestHex.r}`
      );

      cachedTargeting = await res.json();

    } catch (e) {
      cachedTargeting = null;
    }
  }

  const dist = cachedTargeting?.distance ?? "?";
  const los = cachedTargeting?.los ?? "UNKNOWN";
  const path = cachedTargeting?.path ?? [];
  const blocking = cachedTargeting?.blocking ?? [];
  const hindrance = cachedTargeting?.hindrance ?? [];

  // --------------------------------------------------
  // ✅ COLOR SEGÚN LOS
  // --------------------------------------------------
  let color = 0xff0000;

  if (los === "CLEAR") color = 0x00ff00;
  else if (los === "HINDERED") color = 0xffaa00;
  else if (los === "BLOCKED") color = 0xff0000;

  // --------------------------------------------------
  // ✅ VECTOR
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

  // línea 1
  g.moveTo(sx, sy);
  g.lineTo(gapStartX, gapStartY);
  g.stroke({ width: 4, color });

  // línea 2
  g.moveTo(gapEndX, gapEndY);
  g.lineTo(ex, ey);
  g.stroke({ width: 4, color });

  // flecha
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
  // ✅ DRAW PATH (🟣)
  // --------------------------------------------------
  for (let i = 0; i < path.length; i++) {

    const [q, r] = path[i];

    const pos = axialToPixel(q, r);
    const p = world.toGlobal({ x: pos.x, y: pos.y + HEX_SIZE });

    let c = 0xaa00ff;

    if (i === 0) c = 0x0000ff;           // start
    else if (i === path.length - 1) c = 0xff0000; // target

    g.circle(p.x, p.y, 8);
    g.fill({ color: c, alpha: 0.6 });
  }

  // --------------------------------------------------
  // ✅ DRAW HINDRANCE (🟡)
  // --------------------------------------------------
  for (const [q, r] of hindrance) {

    const pos = axialToPixel(q, r);
    const p = world.toGlobal({ x: pos.x, y: pos.y + HEX_SIZE });

    g.circle(p.x, p.y, 10);
    g.stroke({ width: 3, color: 0xffff00 });
  }

  // --------------------------------------------------
  // ✅ DRAW BLOCKING (🔴)
  // --------------------------------------------------
  for (const [q, r] of blocking) {

    const pos = axialToPixel(q, r);
    const p = world.toGlobal({ x: pos.x, y: pos.y + HEX_SIZE });

    g.circle(p.x, p.y, 12);
    g.stroke({ width: 4, color: 0xff0000 });
  }


  // --------------------------------------------------
  // ✅ TEXTO
  // --------------------------------------------------
  debug.text.text = `d=${dist} | LOS=${los}`;
  debug.text.x = mx - debug.text.width / 2;
  debug.text.y = my - debug.text.height / 2;
}