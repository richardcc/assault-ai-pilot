// =================================================
// Assault Application Entry Point
// =================================================

// -------------------------------------------------
// GAME STATE (replay reading phase)
// -------------------------------------------------
window.GAME_STATE = {
  scenario: null,
  replay: null,
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
    const data = await loadApplicationData(replayId);

    if (!data) {
      throw new Error("❌ loadApplicationData devolvió null");
    }

    const { replay, scenario, uiMetadata } = data;

    if (!replay) {
      console.error("❌ Replay NOT loaded");
      return;
    }

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
    // Initialize replay cursor
    // ---------------------------------------------
    GAME_STATE.replayCursor.turnIndex = 0;
    GAME_STATE.replayCursor.eventIndex = 0;

    GAME_STATE.turn = replay.initial_state?.turn ?? 1;
    GAME_STATE.step = 0;

    // ---------------------------------------------
    // ✅ BUILD INITIAL STATE (CRITICAL)
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

    console.log("Replay loaded:", replay);
    console.log("Scenario loaded:", scenario?.id);
    console.log("Players:", GAME_STATE.players);

    // ---------------------------------------------
    // INIT WORLD
    // ---------------------------------------------
    const dom = document.getElementById("slot-map-center");

    if (!window.worldRenderer) {
      console.error("[BOOTSTRAP] worldRenderer not found");
      return;
    }

    if (!window.renderFrame) {
      console.error("[BOOTSTRAP] renderFrame not found");
      return;
    }

    await worldRenderer.init(dom, GAME_STATE);

    // ---------------------------------------------
    // ✅ FIRST RENDER (UI + MAP SYNC INSIDE)
    // ---------------------------------------------
    renderFrame(GAME_STATE, UI_STATE);

  } catch (err) {
    console.error("Bootstrap error:", err);
  }
}

// Run once DOM is ready
document.addEventListener("DOMContentLoaded", bootstrapApplication);