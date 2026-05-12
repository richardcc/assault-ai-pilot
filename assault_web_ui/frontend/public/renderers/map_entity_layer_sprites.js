// =================================================
// MAP ENTITY LAYER (SPRITES) – DEBUG VERSION
// Draws a red circle on hex (1,1) to verify camera
// =================================================

window.mapEntityLayerSprites = (function () {

  let mapView = null;
  let container = null;

  // Debug graphics
  let debugCircle = null;

  // -------------------------------------------------
  // INIT
  // -------------------------------------------------
  function init(boundMapView, pixiApp) {
    mapView = boundMapView;

    container = new PIXI.Container();
    pixiApp.stage.addChild(container);

    // Create debug circle
    debugCircle = new PIXI.Graphics();
    debugCircle.beginFill(0xff0000); // red
    debugCircle.drawCircle(0, 0, 15);
    debugCircle.endFill();

    container.addChild(debugCircle);
  }

  // -------------------------------------------------
  // SYNC (CALLED EVERY FRAME)
  // -------------------------------------------------
  function sync() {
    if (!mapView) return;

    // ✅ APPLY THE SAME CAMERA AS THE MAP
    const cam = UI_STATE.camera;

    container.position.set(-cam.x, -cam.y);
    container.scale.set(cam.zoom, cam.zoom);

    // ✅ PLACE DEBUG CIRCLE AT HEX (1,1)
    const pos = mapView.hexToWorld(1, 1);

    debugCircle.x = pos.x;
    debugCircle.y = pos.y;
  }

  // -------------------------------------------------
  // PUBLIC API
  // -------------------------------------------------
  return {
    init,
    sync
  };
})();
