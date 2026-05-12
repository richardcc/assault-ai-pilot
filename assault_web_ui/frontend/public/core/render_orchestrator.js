// =================================================
// RENDER ORCHESTRATOR
// =================================================

// -------------------------------------------------
// HELPERS
// -------------------------------------------------

function mountRenderer(slotId, renderFn) {
  const slot = document.getElementById(slotId);
  if (!slot) return;
  slot.innerHTML = "";
  renderFn(slot);
}

function toggleSlotVisibility(slotId, visible) {
  const slot = document.getElementById(slotId);
  if (!slot) return;
  slot.style.display = visible ? "" : "none";
}

// -------------------------------------------------
// MAP VIEW (PERSISTENT – SELF-RENDERING)
// -------------------------------------------------

let mapView = null;
let mapEntityLayerMounted = false;
let mapEntityLayerSpritesMounted = false;
let PIXI_APP = null;

function mountMap(gameState) {
  const container = document.getElementById("slot-map-center");
  if (!container) return;

  if (mapView) return;

  mapView = window.renderMapView(gameState);
  mapView.mount(container);

  console.log("MAP VIEW MOUNTED (self-rendering)");

  // Disable old canvas entity layer
  if (!mapEntityLayerMounted && window.mapEntityLayer) {
    console.log("[ORCHESTRATOR] canvas entity layer DISABLED");
    mapEntityLayerMounted = true;
  }

  // Init PIXI overlay
  if (!PIXI_APP) {
    PIXI_APP = new PIXI.Application({
      resizeTo: container,
      backgroundAlpha: 0,
      antialias: true
    });

    PIXI_APP.view.style.position = "absolute";
    PIXI_APP.view.style.top = "0";
    PIXI_APP.view.style.left = "0";
    PIXI_APP.view.style.pointerEvents = "none";
    PIXI_APP.view.style.zIndex = "20";

    container.appendChild(PIXI_APP.view);
  }

  if (!mapEntityLayerSpritesMounted && window.mapEntityLayerSprites) {
    mapEntityLayerSprites.init(mapView, PIXI_APP);
    mapEntityLayerSpritesMounted = true;
  }
}

// -------------------------------------------------
// PUBLIC ENTRY POINT
// -------------------------------------------------

window.renderFrame = function renderFrame(gameState, uiState) {
  renderHeaderSlots(gameState, uiState);
  renderMainSlots(gameState, uiState);
  renderFooterSlots(gameState, uiState);
  renderOverlaySlots(gameState, uiState);

  mountMap(gameState);

  // ✅ JUST sync sprites
  if (window.mapEntityLayerSprites) {
    mapEntityLayerSprites.sync(GAME_STATE.units);
  }
};

// -------------------------------------------------
// HEADER / MAIN / FOOTER / OVERLAYS (igual que antes)
// -------------------------------------------------

// -------------------------------------------------
// HEADER
// -------------------------------------------------

function renderHeaderSlots(gameState, uiState) {
  if (!uiState.panels.header.visible) {
    toggleSlotVisibility("app-header", false);
    return;
  }

  toggleSlotVisibility("app-header", true);

  const headerView = renderHeaderView(gameState);
  mountRenderer("slot-header-left", headerView.left);
  mountRenderer("slot-header-center", headerView.center);
  mountRenderer("slot-header-right", headerView.right);
}


// -------------------------------------------------
// MAIN
// -------------------------------------------------

function renderMainSlots(gameState, uiState) {

  mountRenderer("slot-rag-left", () => {});

  toggleSlotVisibility("slot-log-right", uiState.panels.log.visible);
  if (uiState.panels.log.visible) {
    mountRenderer("slot-log-right", () => {});
  }
}


// -------------------------------------------------
// FOOTER
// -------------------------------------------------

function renderFooterSlots(gameState, uiState) {

  toggleSlotVisibility(
    "slot-footer-left",
    uiState.panels.footer.unitState.visible
  );

  if (uiState.panels.footer.unitState.visible) {
    mountRenderer("slot-footer-left", container => {
      if (window.renderUnitStateView) {
        window.renderUnitStateView(gameState).render(container);
      }
    });
  }

  toggleSlotVisibility(
    "slot-footer-right",
    uiState.panels.footer.combat.visible
  );
}


// -------------------------------------------------
// OVERLAYS
// -------------------------------------------------

function renderOverlaySlots(gameState, uiState) {
  if (uiState.overlays.popup) {
    mountRenderer("overlay-root", () => {});
  }
}
