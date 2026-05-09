import { hexToWorld, HEX_W } from "./grid.js";

/* ===============================
   Image cache & data
   =============================== */
const imageCache = {};
let counterCatalog = null;
let unitVisualMap = null;

// ✅ Keep last rendered positions for animation
const lastPositions = new Map();
const ANIMATION_DURATION = 300; // ms

/* ===============================
   Load counter catalog
   =============================== */
async function loadCounterCatalog() {
  if (counterCatalog) return counterCatalog;
  const response = await fetch("/assets/counter_catalog.json");
  counterCatalog = await response.json();
  return counterCatalog;
}

/* ===============================
   Load unit visual map
   =============================== */
async function loadUnitVisualMap() {
  if (unitVisualMap) return unitVisualMap;
  const response = await fetch("/assets/unit_visual_map.json");
  unitVisualMap = await response.json();
  return unitVisualMap;
}

/* ===============================
   Image cache
   =============================== */
function loadImage(src) {
  if (imageCache[src]) return imageCache[src];
  const img = new Image();
  img.src = src;
  img.onerror = () => {
    console.error("Failed to load image:", src);
  };
  imageCache[src] = img;
  return img;
}

/* ===============================
   Parse hex ("B3", "(1,2)", [1,2])
   =============================== */
function parseHex(hex) {
  if (typeof hex === "string" && hex.includes("(")) {
    const m = hex.match(/-?\d+/g);
    if (m && m.length >= 2) {
      return [parseInt(m[0], 10), parseInt(m[1], 10)];
    }
  }

  if (typeof hex === "string") {
    const letter = hex[0].toUpperCase();
    const number = parseInt(hex.slice(1), 10);
    if (!isNaN(number)) {
      return [
        letter.charCodeAt(0) - "A".charCodeAt(0),
        number - 1
      ];
    }
  }

  if (Array.isArray(hex) && hex.length >= 2) {
    return [hex[0], hex[1]];
  }

  return null;
}

/* ===============================
   Resolve visual catalog key
   =============================== */
function resolveCatalogKey(unit) {
  if (!unitVisualMap) return null;

  const byCounter = unitVisualMap[unit.counter];
  if (!byCounter) return null;

  return byCounter[unit.side] || null;
}

/* ===============================
   Choose sprite (full / half)
   =============================== */
function chooseSprite(unit) {
  if (!counterCatalog || !unitVisualMap) return null;

  const key = resolveCatalogKey(unit);
  if (!key) return null;

  const entry = counterCatalog[key];
  if (!entry) return null;

  const isHalf = unit.strength <= unit.max_strength / 2;
  return `/assets/counters/${isHalf ? entry.half : entry.full}`;
}

/* ===============================
   Draw fallback circle
   =============================== */
function drawUnitFallback(ctx, x, y, unit) {
  ctx.beginPath();
  ctx.arc(x, y, HEX_W * 0.2, 0, Math.PI * 2);
  ctx.fillStyle = unit.side === "IT" ? "#0044cc" : "#cc0000";
  ctx.fill();
}

/* ===============================
   Linear interpolation
   =============================== */
function lerp(a, b, t) {
  return a + (b - a) * t;
}

/* ===============================
   Draw all units (WITH ANIMATION)
   =============================== */
export async function drawUnits(ctx, camera, units) {
  await loadCounterCatalog();
  await loadUnitVisualMap();

  const now = performance.now();

  for (const unit of units) {
    const coords = parseHex(unit.hex);
    if (!coords) continue;

    const worldPos = hexToWorld(coords[0], coords[1]);
    let targetX = worldPos.x;
    let targetY = worldPos.y;

    const last = lastPositions.get(unit.unit_id);

    let drawX = targetX;
    let drawY = targetY;

    if (last && last.toX === targetX && last.toY === targetY) {
      const t = Math.min((now - last.start) / ANIMATION_DURATION, 1);
      drawX = lerp(last.fromX, last.toX, t);
      drawY = lerp(last.fromY, last.toY, t);

      if (t >= 1) {
        lastPositions.delete(unit.unit_id);
      }
    } else {
      // New movement: set animation
      lastPositions.set(unit.unit_id, {
        fromX: last ? last.toX : targetX,
        fromY: last ? last.toY : targetY,
        toX: targetX,
        toY: targetY,
        start: now
      });
    }

    const screenX = (drawX - camera.x) * camera.zoom;
    const screenY = (drawY - camera.y) * camera.zoom;

    const spritePath = chooseSprite(unit);
    if (!spritePath) {
      drawUnitFallback(ctx, screenX, screenY, unit);
      continue;
    }

    const img = loadImage(spritePath);
    if (!img.complete || img.naturalWidth === 0) {
      drawUnitFallback(ctx, screenX, screenY, unit);
      continue;
    }

    const size = HEX_W * 0.65 * camera.zoom;
    ctx.drawImage(
      img,
      screenX - size / 2,
      screenY - size / 2,
      size,
      size
    );
  }
}