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
    // Initialize units FROM REPLAY (reusing scenario initializer)
    // ---------------------------------------------
    const replayScenarioView =
      adaptReplayInitialStateToScenario(GAME_STATE.replay);

    GAME_STATE.units = await initializeUnitsFromScenario(
      replayScenarioView
    );

    // Override HP from replay (replay is the authority)
    for (const unit of Object.values(GAME_STATE.units)) {
      const replayUnit =
        GAME_STATE.replay.initial_state.units.find(u => u.id === unit.unit_id);
      if (replayUnit) {
        unit.hp = replayUnit.hp;
      }
    }


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
    // Sync turn / step counters
    updateTurnStepFromCursor(GAME_STATE);
    renderFrame(GAME_STATE, UI_STATE);

  } catch (err) {
    console.error("Bootstrap error:", err);
  }
}

// Run once DOM is ready
document.addEventListener("DOMContentLoaded", bootstrapApplication);