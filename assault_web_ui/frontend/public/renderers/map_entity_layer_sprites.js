// =================================================
// MAP ENTITY LAYER (PIXI)
// ✅ FINAL VERSION: labels + markers + animation + ux
// =================================================

window.mapEntityLayerSprites = (function () {

  let container = null;
  const sprites = {};

  // -------------------------------------------------
  function init(world) {
    if (container) return;

    container = new PIXI.Container();
    container.name = "mapEntityLayer";
    world.addChild(container);
  }

  // -------------------------------------------------
  function applyScaleOnce(sprite) {
    if (sprite.__scaled) return;

    const tex = sprite.texture;
    const width = tex?.orig?.width || tex?.width || 64;

    const desiredSize = HexGeometry.R * 1.6;
    const scale = desiredSize / width;

    sprite.scale.set(scale);
    sprite.__scaled = true;
  }

  // -------------------------------------------------
  function clearMarkers(sprite) {
    sprite.children
      .filter(c => c.__marker)
      .forEach(c => sprite.removeChild(c));
  }

  function clearLabel(sprite) {
    sprite.children
      .filter(c => c.__label)
      .forEach(c => sprite.removeChild(c));
  }

  // -------------------------------------------------
  // ✅ LABEL PRO (DINÁMICO + COLOR + ZOOM)
  // -------------------------------------------------
  function addUnitLabel(sprite, unit) {

    const unitName = unit.unit_id;

    // ✅ color por facción
    let color = "#ffffff";
    if (unit.side === "US") color = "#4da6ff";
    if (unit.side === "GE") color = "#ff4d4d";

    // ✅ ocultar en zoom out
    const zoom = window.UI_STATE?.camera?.zoom || 1;
    if (zoom < 0.6) return;

    // --------------------------
    // ✅ SOLO ID
    // --------------------------
    const idText = new PIXI.Text(unitName, {
      fontSize: 14,               // un poco más grande
      fill: color,
      stroke: "#000000",
      strokeThickness: 4,

      dropShadow: true,
      dropShadowColor: "#000000",
      dropShadowDistance: 2,
      dropShadowBlur: 2
    });

    idText.anchor.set(0.5);

    // ✅ POSICIÓN PERFECTA (debajo de la unidad)
    idText.y = 65;

    idText.__label = true;

    sprite.addChild(idText);
  }


  // -------------------------------------------------
  // ✅ MARKER ARRIBA DERECHA
  // -------------------------------------------------
  function addMarker(sprite, texturePath, scale = 0.65) {
    if (!texturePath) return;

    const tex = PIXI.Texture.from(texturePath);
    const marker = new PIXI.Sprite(tex);

    marker.anchor.set(0.5);

    // ✅ posición UX correcta
    marker.x = -15;
    marker.y = -25;

    marker.scale.set(scale);
    marker.__marker = true;

    sprite.addChild(marker);
  }

  // -------------------------------------------------
  function applyUnitMarkers(sprite, unit) {

    const markers = window.MARKERS_METADATA;
    if (!markers) return;

    const side = unit.side;

    // DEAD (prioridad)
    if (unit.hp <= 0) {
      addMarker(sprite, markers.DEAD?.[side], 0.7);
      return;
    }

    // SUPPRESSED
    if (unit.status?.includes("SUPPRESSED")) {
      addMarker(sprite, markers.SUPPRESSED?.[side], 0.7);
    }
  }

  // -------------------------------------------------
  function setupInteractivity(sprite, unit) {
    sprite.eventMode = "static";
    sprite.cursor = "pointer";

    sprite.removeAllListeners();

    sprite.on("pointerover", () => {
      window.highlightSidebarUnit?.(unit.unit_id);
    });

    sprite.on("pointerdown", () => {
      window.selectUnit?.(unit.unit_id);
    });
  }

  // -------------------------------------------------
  function createSprite(unit) {
    const key = unit.unit_key || unit.type;
    const def = GAME_STATE.uiMetadata?.units?.[key];
    if (!def) return null;

    const sprite = PIXI.Sprite.from(`/public/assets/counters/${def.full}`);

    sprite.anchor.set(0.5);
    sprite.unitId = unit.unit_id;

    sprite.__scaled = false;
    sprite.__moving = false;

    return sprite;
  }

  // -------------------------------------------------
  function sync(gameState) {
    if (!gameState || !container) return;

    const units = gameState.units;
    const grid = gameState.scenario?.map?.grid;
    if (!units || !grid) return;

    const seen = new Set();

    Object.values(units).forEach(unit => {

      let sprite = sprites[unit.unit_id];

      // CREATE
      if (!sprite) {
        sprite = createSprite(unit);
        if (!sprite) return;

        sprites[unit.unit_id] = sprite;
        container.addChild(sprite);
      }

      applyScaleOnce(sprite);

      // POSITION
      const { q, r } = unit.position || {};
      const prevQ = sprite.__lastQ;
      const prevR = sprite.__lastR;
    
      if (q === undefined) return;

      const pos = hexToWorld(q, r, grid);

      if (!sprite.__initialized) {
        sprite.x = pos.x;
        sprite.y = pos.y;
        sprite.__initialized = true;
      }

      const dx = Math.abs(sprite.x - pos.x);
      const dy = Math.abs(sprite.y - pos.y);
      const moved = dx > 1 || dy > 1;

      // ✅ animación movimiento
      if ((sprite.__lastQ !== q || sprite.__lastR !== r) && !sprite.__moving) {

        if (typeof animateUnitMove === "function") {

          sprite.__moving = true;

          animateUnitMove(
            sprite,
            { q, r },
            {
              R: HexGeometry.R,
              ROW: HexGeometry.ROW ?? (1.5 * HexGeometry.R),
              W: HexGeometry.W ?? (Math.sqrt(3) * HexGeometry.R)
            },
            PIXI.Ticker.shared,
            400,
            () => sprite.__moving = false
          );
        }
      }


      // visuals
      clearMarkers(sprite);
      clearLabel(sprite);

      addUnitLabel(sprite, unit);
      applyUnitMarkers(sprite, unit);
      setupInteractivity(sprite, unit);

      sprite.alpha = unit.alive === false ? 0.4 : 1;

      seen.add(unit.unit_id);
    });

    // cleanup
    Object.keys(sprites).forEach(id => {
      if (!seen.has(id)) {
        container.removeChild(sprites[id]);
        sprites[id].destroy();
        delete sprites[id];
      }
    });
  }

  function getUnitSprite(id) {
    return sprites[id] || null;
  }

  return { init, sync, getUnitSprite };

})();
