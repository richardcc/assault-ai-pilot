// -------------------------------------------------
// Unit Renderer
// -------------------------------------------------
// Renders unit counters on the map using hex (q,r)
// Does NOT touch grid, camera, pan or zoom
// -------------------------------------------------

let unitLayer = null;
let hostContainer = null;

function renderUnitsOnMap(app, scenario) {

  if (!scenario || !Array.isArray(scenario.units)) {
    console.warn("renderUnitsOnMap: scenario.units missing or invalid");
    return;
  }

  // -------------------------------------------------
  // ✅ ROBUST HOST CONTAINER DETECTION
  // -------------------------------------------------
  if (!hostContainer) {
    // Use the first PIXI.Container created by map_renderer
    hostContainer = app.stage.children.find(c => c instanceof PIXI.Container);

    if (!hostContainer) {
      console.error("renderUnitsOnMap: no container found on stage");
      return;
    }
  }

  // -------------------------------------------------
  // ✅ CREATE UNIT LAYER ONCE
  // -------------------------------------------------
  if (!unitLayer) {
    unitLayer = new PIXI.Container();
    unitLayer.name = "unitLayer";
    hostContainer.addChild(unitLayer);
  }

  // ✅ CLEAR PREVIOUS UNITS (CRITICAL)
  unitLayer.removeChildren();

  // -------------------------------------------------
  // Grid geometry (must match map_renderer)
  // -------------------------------------------------
  const R   = scenario.grid.hexRadius;
  const W   = Math.sqrt(3) * R;
  const ROW = 1.5 * R;

  function hexToWorld(q, r) {
    return {
      x: q * W + (r % 2) * (W / 2),
      y: r * ROW
    };
  }

  // -------------------------------------------------
  // Render units
  // -------------------------------------------------
  scenario.units.forEach(unit => {

    // Skip units not on map (dead / not deployed)
    if (typeof unit.q !== "number" || typeof unit.r !== "number") {
      return;
    }

    if (!unit.image) {
      console.warn("Unit without image:", unit);
      return;
    }

    const tex = PIXI.Texture.from(unit.image);
    const spr = new PIXI.Sprite(tex);

    const pos = hexToWorld(unit.q, unit.r);

    spr.anchor.set(0.5);
    spr.x = pos.x;
    spr.y = pos.y;
    spr.scale.set(0.5);

    // Metadata (future use: selection, highlight, etc.)
    spr.unitId = unit.id;
    spr.side = unit.side;

    unitLayer.addChild(spr);
  });
}

// -------------------------------------------------
// ✅ EXPOSE FUNCTION GLOBALLY
// -------------------------------------------------
window.renderUnitsOnMap = renderUnitsOnMap;
