// =================================================
// MAP ENTITY LAYER (PIXI)
// Sprite creation, scaling and animation decision
// Safe revive of dead units (no invisible / no giant)
// =================================================

window.mapEntityLayerSprites = (function () {

  let container = null;
  const sprites = {};

  // -------------------------------------------------
  // INIT
  // -------------------------------------------------
  function init(world) {
    if (container) return;
    container = new PIXI.Container();
    container.name = "mapEntityLayer";
    world.addChild(container);
  }

  // -------------------------------------------------
  // Apply scale ONCE, using stable texture dimensions
  // -------------------------------------------------
  function applyScaleOnce(sprite) {
    if (sprite.__scaled) return;

    const tex = sprite.texture;
    const width =
      tex?.orig?.width ||
      tex?.baseTexture?.realWidth ||
      0;

    if (!width) return; // texture not ready

    const desiredSize = HexGeometry.R * 1.6; // ~85% hex
    const scale = desiredSize / width;

    sprite.scale.set(scale);
    sprite.__scaled = true;
  }

  // -------------------------------------------------
  // Finalize sprite when texture is ready
  // -------------------------------------------------
  function finalizeSprite(sprite, q, r) {
    applyScaleOnce(sprite);
    snapUnitToHex(sprite, q, r);
    sprite.alpha = 1;
  }

  // -------------------------------------------------
  // SYNC UNITS
  // -------------------------------------------------
  function sync(units) {
    if (!units || !container) return;

    const alive = new Set();

    const grid = {
      R: HexGeometry.R,
      ROW: HexGeometry.ROW ?? (1.5 * HexGeometry.R),
      W: HexGeometry.W ?? (Math.sqrt(3) * HexGeometry.R)
    };

    Object.values(units).forEach(unit => {
      if (!unit.alive) return;
      alive.add(unit.unit_id);

      let sprite = sprites[unit.unit_id];

      // -------------------------------------------------
      // CREATE SPRITE (new or revived unit)
      // -------------------------------------------------
      if (!sprite) {
        const def = GAME_STATE.uiMetadata?.units?.[unit.unit_key];
        if (!def) return;

        sprite = PIXI.Sprite.from(`/public/art/counters/${def.full}`);
        sprite.anchor.set(0.5);
        sprite.unitId = unit.unit_id;

        sprite.alpha = 0;          // hide until ready
        sprite.__scaled = false;

        sprites[unit.unit_id] = sprite;
        container.addChild(sprite);

        sprite.__lastQ = unit.position.q;
        sprite.__lastR = unit.position.r;

        // Texture loaded?
        if (sprite.texture.baseTexture.valid) {
          finalizeSprite(
            sprite,
            unit.position.q,
            unit.position.r
          );
        } else {
          sprite.texture.baseTexture.once("loaded", () => {
            finalizeSprite(
              sprite,
              unit.position.q,
              unit.position.r
            );
          });
        }

        return;
      }

      // -------------------------------------------------
      // EXISTING SPRITE
      // -------------------------------------------------
      applyScaleOnce(sprite);

      const toQ = unit.position.q;
      const toR = unit.position.r;

      if (
        GAME_STATE.__renderMode === "incremental" &&
        (sprite.__lastQ !== toQ || sprite.__lastR !== toR)
      ) {
        animateUnitMove(
          sprite,
          { q: toQ, r: toR },
          grid,
          PIXI.Ticker.shared,
          700
        );
      } else {
        snapUnitToHex(sprite, toQ, toR);
        sprite.__lastQ = toQ;
        sprite.__lastR = toR;
      }
    });

    // -------------------------------------------------
    // CLEAN UP DEAD UNITS
    // -------------------------------------------------
    Object.keys(sprites).forEach(id => {
      if (!alive.has(id)) {
        sprites[id].destroy();
        delete sprites[id];
      }
    });
  }

  // -------------------------------------------------
  // ✅ PUBLIC API — sprite access for attack animations
  // -------------------------------------------------
  function getUnitSprite(unitId) {
    return sprites[unitId] || null;
  }

  // -------------------------------------------------
  // EXPORT
  // -------------------------------------------------
  return {
    init,
    sync,
    getUnitSprite
  };

})();