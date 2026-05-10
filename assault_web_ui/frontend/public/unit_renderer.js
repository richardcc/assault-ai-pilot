// -------------------------------------------------
// Unit Renderer
// -------------------------------------------------
// Renders unit counters on the map using hex (q,r)
// Animates movement visually (no pending, no state delay)
// -------------------------------------------------

let unitLayer = null;
let hostContainer = null;

// Store sprites by unitId
const unitSprites = new Map();

function renderUnitsOnMap(app, scenario) {

  if (!scenario || !Array.isArray(scenario.units)) {
    console.warn("renderUnitsOnMap: scenario.units missing or invalid");
    return;
  }

  // -------------------------------------------------
  // Get camera container (created by map_renderer)
  // -------------------------------------------------
  if (!hostContainer) {
    hostContainer = app.stage.children.find(
      c => c instanceof PIXI.Container
    );

    if (!hostContainer) {
      console.error("renderUnitsOnMap: no camera container found");
      return;
    }
  }

  // -------------------------------------------------
  // Create unit layer once
  // -------------------------------------------------
  if (!unitLayer) {
    unitLayer = new PIXI.Container();
    unitLayer.name = "unitLayer";
    hostContainer.addChild(unitLayer);
  }

  // -------------------------------------------------
  // Grid geometry (MUST MATCH map_renderer)
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
  // Mark all sprites as unused this frame
  // -------------------------------------------------
  unitSprites.forEach(sprite => {
    sprite.__usedThisFrame = false;
  });

  // -------------------------------------------------
  // Render or update units
  // -------------------------------------------------
  scenario.units.forEach(unit => {

    if (typeof unit.q !== "number" || typeof unit.r !== "number") {
      return;
    }

    const pos = hexToWorld(unit.q, unit.r);
    let sprite = unitSprites.get(unit.id);

    if (!sprite) {
      // ---------------- NEW UNIT ----------------
      if (!unit.image) return;

      const tex = PIXI.Texture.from(unit.image);
      sprite = new PIXI.Sprite(tex);

      sprite.anchor.set(0.5);
      sprite.scale.set(0.5);
      sprite.x = pos.x;
      sprite.y = pos.y;

      sprite.unitId = unit.id;
      sprite.side = unit.side;

      unitLayer.addChild(sprite);
      unitSprites.set(unit.id, sprite);

    } else {
      // ---------------- EXISTING UNIT ----------------
      // Animate from current sprite position to new hex
      animateUnitMove(
        sprite,
        unit,     // uses q/r
        { R, W, ROW },
        app,
        700       // stepDuration (visual only)
      );
    }

    sprite.__usedThisFrame = true;
  });

  // -------------------------------------------------
  // Remove sprites for units no longer present
  // -------------------------------------------------
  unitSprites.forEach((sprite, id) => {
    if (!sprite.__usedThisFrame) {
      unitLayer.removeChild(sprite);
      unitSprites.delete(id);
    }
  });
}

// -------------------------------------------------
// Public API
// -------------------------------------------------
window.renderUnitsOnMap = renderUnitsOnMap;