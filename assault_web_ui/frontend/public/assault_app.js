// =================================================
// Assault Application Entry Point
// =================================================

// -------------------------------------------------
// GAME STATE (replay reading phase)
// -------------------------------------------------
window.GAME_STATE = {
  scenario: null,
  replay: null,
  units: [],
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
    // SINGLE application load (replay + scenario + UI)
    // ---------------------------------------------
    const {
      replay,
      scenario,
      uiMetadata
    } = await loadApplicationData(replayId);
    
    // ---------------------------------------------
    // Store loaded data in GAME_STATE
    // ---------------------------------------------
    GAME_STATE.replay = replay;
    GAME_STATE.scenario = scenario;
    GAME_STATE.uiMetadata = uiMetadata;

    // ---------------------------------------------
    // Initialize units into GAME_STATE (minimal, safe)
    // ---------------------------------------------
    GAME_STATE.units = await initializeUnitsFromScenario(
      GAME_STATE.scenario
    );

    // ---------------------------------------------
    // Initialize replay cursor
    // ---------------------------------------------
    GAME_STATE.replayCursor.turnIndex = 0;
    GAME_STATE.replayCursor.eventIndex = 0;

    // Expose basic turn/step for UI (read-only)
    GAME_STATE.turn = replay.initial_state?.turn ?? 1;
    GAME_STATE.step = 0;

    // ---------------------------------------------
    // Extract players from replay metadata
    // ---------------------------------------------
    const replaySides = replay.meta?.sides ?? {};

    GAME_STATE.players = Object.entries(replaySides).map(
      ([sideId, controllerId]) => ({
        sideId,
        controllerId
      })
    );

    console.log("Replay loaded:", replay.id);
    console.log(
      "Scenario loaded:",
      scenario ? scenario.id : "(none)"
    );
    console.log("Players:", GAME_STATE.players);

    // ---------------------------------------------
    // First render
    // ---------------------------------------------
    renderFrame(GAME_STATE, UI_STATE);

  } catch (err) {
    console.error("Bootstrap error:", err);
  }
}

// Run once DOM is ready
document.addEventListener("DOMContentLoaded", bootstrapApplication);