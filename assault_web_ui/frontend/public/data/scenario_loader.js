// =================================================
// SCENARIO LOADER (raw scenario JSON)
// =================================================

window.loadScenario = async function loadScenario(scenarioId) {
  const url = `http://127.0.0.1:8000/api/scenarios/${scenarioId}`;

  try {
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Failed to load scenario: ${scenarioId}`);
    }

    const scenarioData = await response.json();
    return scenarioData;
  } catch (err) {
    console.error("Scenario loading error:", err);
    throw err;
  }
};