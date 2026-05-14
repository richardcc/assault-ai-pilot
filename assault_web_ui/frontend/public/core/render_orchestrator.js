// =================================================
// RENDER ORCHESTRATOR
// UI only – world logic lives in world_renderer
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
// PUBLIC ENTRY POINT
// -------------------------------------------------
window.renderFrame = function renderFrame(gameState, uiState) {

  console.log("=================================================");
  console.log("[RENDER FRAME] START");
  console.log("[RENDER FRAME] units keys:", Object.keys(gameState.units || {}));
  console.log("[RENDER FRAME] units:", gameState.units);
  console.log("[RENDER FRAME] scenario:", gameState.scenario);

  // -------------------------------------------------
  // CORE RENDER
  // -------------------------------------------------
  try {
    renderHeaderSlots(gameState, uiState);
    renderMainSlots(gameState, uiState);
    renderFooterSlots(gameState, uiState);
    renderOverlaySlots(gameState, uiState);
  } catch (e) {
    console.error("[RENDER FRAME] UI ERROR:", e);
  }

  // -------------------------------------------------
  // ✅ CRITICAL: UPDATE WORLD MAP
  // -------------------------------------------------
  if (window.worldRenderer) {
    console.log("[RENDER FRAME] calling worldRenderer.updateUnits()");

    try {
      worldRenderer.updateUnits(gameState);
    } catch (e) {
      console.error("[RENDER FRAME] ERROR updateUnits:", e);
    }

  } else {
    console.warn("[RENDER FRAME] worldRenderer NOT FOUND");
  }

  console.log("[RENDER FRAME] END");
};

// -------------------------------------------------
// HEADER
// -------------------------------------------------
function renderHeaderSlots(gameState, uiState) {

  if (!uiState.panels.header.visible) {
    toggleSlotVisibility("app-header", false);
    return;
  }

  toggleSlotVisibility("app-header", true);

  try {
    const headerView = renderHeaderView(gameState);

    mountRenderer("slot-header-left", headerView.left);
    mountRenderer("slot-header-center", headerView.center);
    mountRenderer("slot-header-right", headerView.right);

  } catch (e) {
    console.error("[HEADER] render error:", e);
  }
}

// -------------------------------------------------
// MAIN
// -------------------------------------------------
function renderMainSlots(gameState, uiState) {

  const container = document.getElementById("slot-rag-left");
  if (!container) {
    console.warn("[MAIN] slot-rag-left missing");
    return;
  }

  // ---------------------------------------------
  // INIT LEFT COLUMN ONCE
  // ---------------------------------------------
  if (!container.__ragInitialized) {

    console.log("[MAIN] Initializing left column");

    const column = document.createElement("div");
    column.id = "rag-left-column";
    column.className = "rag-left-column";

    const chatDiv = document.createElement("div");
    chatDiv.id = "rag-chat";
    chatDiv.className = "rag-pane";
    column.appendChild(chatDiv);

    const hrlDiv = document.createElement("div");
    hrlDiv.id = "hrl-explanation";
    hrlDiv.className = "hrl-pane";
    column.appendChild(hrlDiv);

    const tacticalDiv = document.createElement("div");
    tacticalDiv.id = "tactical-explanation";
    tacticalDiv.className = "tactical-pane";
    column.appendChild(tacticalDiv);

    container.innerHTML = "";
    container.appendChild(column);

    container.__ragInitialized = true;

    clearHRLExplanation?.();
    clearTacticalExplanation?.();
  }

  // ---------------------------------------------
  // RIGHT LOG PANEL
  // ---------------------------------------------
  toggleSlotVisibility("slot-log-right", uiState.panels.log.visible);

  if (uiState.panels.log.visible) {
    mountRenderer("slot-log-right", container => {

      const logDiv = document.createElement("div");
      logDiv.id = "event-log";
      logDiv.className = "event-log";

      container.appendChild(logDiv);

      if (window.rebuildEventLogFromState) {
        rebuildEventLogFromState(gameState);
      }
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

  if (uiState.panels.footer.combat.visible) {
    const slot = document.getElementById("slot-footer-right");

    if (slot && !slot.__combatMounted) {
      if (window.renderCombatHostView) {
        window.renderCombatHostView(slot);
        slot.__combatMounted = true;
      }
    }
  }
}

// -------------------------------------------------
// OVERLAYS
// -------------------------------------------------
function renderOverlaySlots(gameState, uiState) {
  // Future extensions
}