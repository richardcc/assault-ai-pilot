// =================================================
// Assault Application Entry Point
// =================================================

// -------------------------------------------------
// GAME STATE (replay reading phase)
// -------------------------------------------------
window.GAME_STATE = {
  scenario: null,
  replay: null,

  // IMPORTANT: units must be an object keyed by unit_id
  units: {},

  turn: 0,
  step: 0,

  replayCursor: {
    turnIndex: 0,
    eventIndex: 0
  },

  uiMetadata: null,
  players: []
};

// -------------------------------------------------
// Application bootstrap
// -------------------------------------------------
async function bootstrapApplication() {
  console.log("Assault application bootstrap");

  const replayId =
    "phase01_seq001_initial_contact__US_RL_vs_GE_HEURISTIC";

  try {
    // ---------------------------------------------
    // Load replay + scenario + UI metadata
    // ---------------------------------------------
    const {
      replay,
      scenario,
      uiMetadata
    } = await loadApplicationData(replayId);

    GAME_STATE.replay = replay;
    GAME_STATE.scenario = scenario;
    GAME_STATE.uiMetadata = uiMetadata;

    // ---------------------------------------------
    // Build MAP UI data
    // ---------------------------------------------
    GAME_STATE.uiMetadata.mapUi = buildMapUi(GAME_STATE);

    if (!GAME_STATE.uiMetadata.mapUi) {
      console.error("[BOOTSTRAP] Failed to build mapUi");
    } else {
      console.log("[BOOTSTRAP] mapUi built");
    }

    // ---------------------------------------------
    // Initialize replay cursor (START OF REPLAY)
    // ---------------------------------------------
    GAME_STATE.replayCursor.turnIndex = 0;
    GAME_STATE.replayCursor.eventIndex = 0;

    GAME_STATE.turn = replay.initial_state?.turn ?? 1;
    GAME_STATE.step = 0;

    // ---------------------------------------------
    // ✅ BUILD INITIAL REPLAY STATE (CRITICAL)
    // This fills GAME_STATE.units deterministically
    // ---------------------------------------------
    rebuildStateUpToCursor(GAME_STATE);

    // ---------------------------------------------
    // Extract players
    // ---------------------------------------------
    const replaySides = replay.meta?.sides ?? {};

    GAME_STATE.players = Object.entries(replaySides).map(
      ([sideId, controllerId]) => ({
        sideId,
        controllerId
      })
    );

    console.log("Replay loaded:", replay.id);
    console.log("Scenario loaded:", scenario?.id);
    console.log("Players:", GAME_STATE.players);

    // ---------------------------------------------
    // INIT WORLD + FIRST UI RENDER
    // ---------------------------------------------
    const dom = document.getElementById("slot-map-center");

    if (!window.worldRenderer) {
      console.error("[BOOTSTRAP] worldRenderer not found");
      return;
    }

    if (!window.renderFrame) {
      console.error("[BOOTSTRAP] renderFrame (UI orchestrator) not found");
      return;
    }

    // ---------------------------------------------
    // ✅ INIT PIXI WORLD (map + grid + unit layer)
    // ---------------------------------------------
    await worldRenderer.init(dom, GAME_STATE);

    // ---------------------------------------------
    // ✅ RENDER INITIAL UNITS (THIS WAS MISSING)
    // ---------------------------------------------
    worldRenderer.updateUnits(GAME_STATE);

    // ---------------------------------------------
    // First UI render (DOM panels, header, footer, etc.)
    // ---------------------------------------------
    renderFrame(GAME_STATE, UI_STATE);

  } catch (err) {
    console.error("Bootstrap error:", err);
  }
}

// Run once DOM is ready
document.addEventListener("DOMContentLoaded", bootstrapApplication);
