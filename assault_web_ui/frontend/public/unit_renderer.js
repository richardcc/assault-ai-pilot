// -------------------------------------------------
// Unit Renderer
// -------------------------------------------------
// Renders unit counters on the map using hex (q,r)
// Does NOT touch grid, camera, pan or zoom
// -------------------------------------------------

function renderUnitsOnMap(app, scenario) {

  if (!scenario || !Array.isArray(scenario.units)) {
    console.warn("renderUnitsOnMap: scenario.units missing or invalid");
    return;
  }

  // Get camera (created by map_renderer)
  const camera = app.stage.children[0];
  if (!camera) {
    console.error("renderUnitsOnMap: camera not found");
    return;
  }

  // Grid geometry (must match map)
  const R   = scenario.grid.hexRadius;
  const W   = Math.sqrt(3) * R;
  const ROW = 1.5 * R;

  function hexToWorld(q, r) {
    return {
      x: q * W + (r % 2) * (W / 2),
      y: r * ROW
    };
  }

  // Dedicated layer for units
  const unitLayer = new PIXI.Container();
  unitLayer.name = "unitLayer";
  camera.addChild(unitLayer);

  scenario.units.forEach(unit => {

    if (typeof unit.q !== "number" || typeof unit.r !== "number") {
      return; // unit not on map yet
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
    spr.scale.set(0.5); // adjust if needed

    spr.unitId = unit.id;
    spr.side = unit.side;

    unitLayer.addChild(spr);
  });
}

// ✅ EXPOSE FUNCTION GLOBALLY (THIS IS THE KEY FIX)
window.renderUnitsOnMap = renderUnitsOnMap;
