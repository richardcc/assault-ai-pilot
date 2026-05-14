// =================================================
// MAP ENTITY LAYER (Canvas Overlay)
// Renders dynamic world entities (units for now)
// =================================================

window.mapEntityLayer = (function () {

  let canvas = null;
  let ctx = null;
  let mapView = null;
  let rafId = null;

  // -------------------------------------------------
  // IMAGE CACHE (keyed by art filename)
  // -------------------------------------------------
  const unitImages = {};

  function loadUnitImage(unit) {
    const unitDefs = GAME_STATE.uiMetadata?.units;
    const def = unitDefs?.[unit.unit_key];

    if (!def || !def.full) {
      console.warn(
        "[ENTITY LAYER] No art defined for unit_key:",
        unit.unit_key
      );
      return null;
    }

    const artName = def.full;

    if (unitImages[artName]) {
      return unitImages[artName];
    }

    const img = new Image();
    img.src = "/public/art/counters/" + artName;

    img.onerror = () => {
      console.error(
        `[ENTITY LAYER] Failed to load unit image: ${img.src}`
      );
    };

    unitImages[artName] = img;
    return img;
  }

  // -------------------------------------------------
  // INIT (called once by render orchestrator)
  // -------------------------------------------------
  function init(boundMapView, container) {
    mapView = boundMapView;

    canvas = document.createElement("canvas");

    // Match map canvas size exactly
    const baseCanvas = mapView.getCanvas();
    canvas.width  = baseCanvas.width;
    canvas.height = baseCanvas.height;

    // Overlay positioning
    canvas.style.position = "absolute";
    canvas.style.top = "0";
    canvas.style.left = "0";
    canvas.style.width = "100%";
    canvas.style.height = "100%";
    canvas.style.pointerEvents = "none";
    canvas.style.zIndex = "10";
    canvas.classList.add("map-entity-layer");

    container.appendChild(canvas);
    ctx = canvas.getContext("2d");

    renderLoop();
  }

  // -------------------------------------------------
  // RENDER LOOP (persistent)
  // -------------------------------------------------
  function renderLoop() {
    rafId = requestAnimationFrame(renderLoop);
    render();
  }

  function render() {
    if (!ctx || !mapView) return;

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    ctx.save();
    Camera2D.apply(ctx, canvas, UI_STATE.camera);

    if (GAME_STATE.units) {
      Object.values(GAME_STATE.units).forEach(drawUnit);
    }

    ctx.restore();
  }

  // -------------------------------------------------
  // DRAW UNIT COUNTER (aspect-ratio safe)
  // -------------------------------------------------
  function drawUnit(unit) {
    if (!unit.position) return;

    const { q, r } = unit.position;
    const { x, y } = mapView.hexToWorld(q, r);

    const img = loadUnitImage(unit);

    // Only draw if image is valid
    if (!img || !img.complete || img.naturalWidth === 0) {
      return;
    }

    // -------------------------------------------------
    // Size based on hex geometry (NOT hardcoded)
    // Max size = 80% of flat-to-flat hex diameter
    // -------------------------------------------------
    const maxSize = Math.sqrt(3) * HexGeometry.R * 0.8;

    // Preserve original asset aspect ratio
    const aspect = img.naturalWidth / img.naturalHeight;

    let drawWidth, drawHeight;

    if (aspect >= 1) {
      drawWidth  = maxSize;
      drawHeight = maxSize / aspect;
    } else {
      drawHeight = maxSize;
      drawWidth  = maxSize * aspect;
    }

    ctx.drawImage(
      img,
      x - drawWidth / 2,
      y - drawHeight / 2,
      drawWidth,
      drawHeight
    );
  }

  // -------------------------------------------------
  // PUBLIC API
  // -------------------------------------------------
  return {
    init
  };
})();