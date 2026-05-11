// =================================================
// APPLICATION LOADER (single entry point)
// =================================================

window.loadApplicationData = async function loadApplicationData(replayId) {

  // -----------------------------------------------
  // Load replay (using existing loader)
  // -----------------------------------------------
  const replay = await loadReplay(replayId);

  // -----------------------------------------------
  // Load scenario referenced by replay
  // -----------------------------------------------
  let scenario = null;
  const scenarioId = replay.meta?.scenario_id;

  if (scenarioId) {
    scenario = await loadScenario(scenarioId);

    // ---------------------------------------------
    // TEMP: Inject GLOBAL map grid (replay-only)
    // ---------------------------------------------
    injectTemporaryMapGrid(scenario);
  }

  // -----------------------------------------------
  // Load ALL UI metadata (units + map art, same type)
  // -----------------------------------------------
  const uiMetadata = await loadUiMetadata();

  // -----------------------------------------------
  // Unified application payload
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

  scenario.map = scenario.map || {};

  scenario.map.grid = {
    cols: 9,
    rows: 16,
    __temp: true
  };
}