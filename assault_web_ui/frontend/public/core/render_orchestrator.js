// =================================================
// RENDER ORCHESTRATOR
// Central place that coordinates ALL rendering:
//
// - HTML panels (header, footer, sidebars)
// - Persistent renderers (map, future timelines, etc.)
//
// IMPORTANT:
// Persistent renderers (like map) manage their own
// render loops and must NOT be re-rendered here.
// =================================================


// -------------------------------------------------
// HELPERS (MUST BE DEFINED FIRST)
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

function mountMap(gameState) {
  const container = document.getElementById("slot-map-center");
  if (!container) return;

  if (mapView) return; // ✅ already mounted

  if (!window.renderMapView) {
    console.error("renderMapView is not defined");
    return;
  }

  mapView = window.renderMapView(gameState);
  mapView.mount(container);

  console.log("MAP VIEW MOUNTED (self-rendering)");

  // -------------------------------------------------
  // INIT ENTITY LAYER ONCE MAP EXISTS
  // -------------------------------------------------
  if (!mapEntityLayerMounted && window.mapEntityLayer) {
    console.log("[ORCHESTRATOR] init map_entity_layer");

    mapEntityLayer.init(
      mapView,
      container
    );

    mapEntityLayerMounted = true;
  }
} // ✅ ← ESTA LLAVE FALTABA


// -------------------------------------------------
// PUBLIC ENTRY POINT
// -------------------------------------------------

window.renderFrame = function renderFrame(gameState, uiState) {

  // Structural UI
  renderHeaderSlots(gameState, uiState);
  renderMainSlots(gameState, uiState);
  renderFooterSlots(gameState, uiState);
  renderOverlaySlots(gameState, uiState);

  // Persistent renderers
  mountMap(gameState);

};


// -------------------------------------------------
// HEADER
// -------------------------------------------------

function renderHeaderSlots(gameState, uiState) {
  const headerVisible = uiState.panels.header.visible;

  toggleSlotVisibility("app-header", headerVisible);
  if (!headerVisible) return;

  const headerView = renderHeaderView(gameState);

  mountRenderer("slot-header-left", headerView.left);
  mountRenderer("slot-header-center", headerView.center);
  mountRenderer("slot-header-right", headerView.right);
}


// -------------------------------------------------
// MAIN (HTML PANELS ONLY – NO MAP HERE)
// -------------------------------------------------

function renderMainSlots(gameState, uiState) {

  mountRenderer("slot-rag-left", () => {
    // RAG panels renderer will be mounted here
  });

  toggleSlotVisibility(
    "slot-log-right",
    uiState.panels.log.visible
  );

  if (uiState.panels.log.visible) {
    mountRenderer("slot-log-right", () => {
      // event log renderer will be mounted here
    });
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
    mountRenderer("slot-footer-left", (container) => {
      if (window.renderUnitStateView) {
        window.renderUnitStateView(gameState).render(container);
      }
    });
  }

  if (uiState.panels.footer.combat.popup) {
    mountRenderer("overlay-root", () => {
      // combat popup renderer
    });
  } else {
    toggleSlotVisibility(
      "slot-footer-right",
      uiState.panels.footer.combat.visible
    );

    if (uiState.panels.footer.combat.visible) {
      mountRenderer("slot-footer-right", () => {
        // combat panel renderer
      });
    }
  }
}


// -------------------------------------------------
// OVERLAYS
// -------------------------------------------------

function renderOverlaySlots(gameState, uiState) {
  if (uiState.overlays.popup) {
    mountRenderer("overlay-root", () => {
      // generic popup renderer
    });
  }
}