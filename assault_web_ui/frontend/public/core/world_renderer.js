// =================================================
// WORLD RENDERER (PIXI)
// Map + Grid + Units + Pan / Zoom / Rotate
// =================================================

window.worldRenderer = (function () {

  let app = null;
  let world = null;
  let mounted = false;

  const camera = {
    x: 0,
    y: 0,
    zoom: 1,
    rotation: 0
  };

  // -------------------------------------------------
  // INIT WORLD
  // -------------------------------------------------
  async function init(dom, gameState) {
    if (mounted) return;
    mounted = true;

    // ---------------------------------------------
    // PIXI Application
    // ---------------------------------------------
    app = new PIXI.Application({
      resizeTo: dom,
      backgroundColor: 0x111111,
      antialias: true,
      resolution: window.devicePixelRatio || 1,
      autoDensity: true
    });

    dom.appendChild(app.view);

    // ---------------------------------------------
    // Root world container
    // ---------------------------------------------
    world = new PIXI.Container();
    app.stage.addChild(world);

    // ---------------------------------------------
    // 1️⃣ GRID (geometry authority)
    // ---------------------------------------------
    hexGridPixi.init(world, gameState.scenario);
    const gridBounds = hexGridPixi.getBounds();

    if (!gridBounds) {
      console.error("[WORLD] gridBounds missing");
      return;
    }

    // ---------------------------------------------
    // 2️⃣ MAP ART (needs gridBounds)
    // ---------------------------------------------
    await mapLayerPixi.init(
      world,
      gameState.uiMetadata.mapUi,
      gridBounds,
      gameState.scenario.map.grid
    );

    // ---------------------------------------------
    // 3️⃣ ENTITY LAYER (UNITS) — MUST BE LAST
    // ---------------------------------------------
    if (window.mapEntityLayerSprites) {
      mapEntityLayerSprites.init(world);
    } else {
      console.error("[WORLD] mapEntityLayerSprites not found");
    }

    // ---------------------------------------------
    // Center camera on grid
    // ---------------------------------------------
    camera.x = gridBounds.x + gridBounds.width / 2;
    camera.y = gridBounds.y + gridBounds.height / 2;

    // ---------------------------------------------
    // Mouse / Pointer input
    // ---------------------------------------------
    attachPixiMouseInput(app.view, camera);

    // ---------------------------------------------
    // Apply camera every frame
    // ---------------------------------------------
    app.ticker.add(() => {
      applyCamera();
    });

    console.log("[WORLD] initialized correctly");
  }

  // -------------------------------------------------
  // APPLY CAMERA TRANSFORM
  // -------------------------------------------------
  function applyCamera() {
    if (!app || !world) return;

    const w = app.renderer.width;
    const h = app.renderer.height;

    world.position.set(w / 2, h / 2);
    world.scale.set(camera.zoom);
    world.rotation = camera.rotation;
    world.pivot.set(camera.x, camera.y);
  }

  // -------------------------------------------------
  // UPDATE UNITS
  // -------------------------------------------------
  function updateUnits(gameState) {
    if (!gameState?.units) return;
    if (!window.mapEntityLayerSprites) return;

    mapEntityLayerSprites.sync(gameState.units);
  }

  // -------------------------------------------------
  // PUBLIC API
  // -------------------------------------------------
  return {
    init,
    updateUnits
  };

})(); 