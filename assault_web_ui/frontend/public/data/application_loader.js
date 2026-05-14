// =================================================
// APPLICATION LOADER (single entry point)
// =================================================

window.loadApplicationData = async function loadApplicationData(replayId) {

  // -----------------------------------------------
  // Load replay
  // -----------------------------------------------
  const replay = await loadReplay(replayId);

  // ✅ FIX CRÍTICO: validar replay
  if (!replay) {
    console.error("❌ loadReplay() devolvió undefined");
    console.error("❌ replayId:", replayId);

    return {
      replay: null,
      scenario: null,
      uiMetadata: null
    };
  }

  console.log("✅ Replay RAW:", replay);

  // -----------------------------------------------
  // Load scenario referenced by replay
  // -----------------------------------------------
  let scenario = null;

  const scenarioId = replay.meta?.scenario_id;

  if (!scenarioId) {
    console.error("❌ replay.meta.scenario_id missing");
  } else {
    scenario = await loadScenario(scenarioId);

    if (!scenario) {
      console.error("❌ Scenario NOT loaded:", scenarioId);
    } else {
      // ---------------------------------------------
      // TEMP: Inject GLOBAL map grid
      // ---------------------------------------------
      injectTemporaryMapGrid(scenario);
    }
  }

  // -----------------------------------------------
  // Load UI metadata
  // -----------------------------------------------
  const uiMetadata = await loadUiMetadata();

  if (!uiMetadata) {
    console.error("❌ uiMetadata NOT loaded");
  }

  // -----------------------------------------------
  // FINAL PAYLOAD
  // -----------------------------------------------
  return {
    replay,
    scenario,
    uiMetadata
  };
};


// =================================================
// TEMPORARY MAP GRID INJECTION
// =================================================

function injectTemporaryMapGrid(scenario) {

  if (!scenario) return;

  scenario.map = scenario.map || {};

  scenario.map.grid = {
    cols: 9,
    rows: 16,
    __temp: true
  };
}