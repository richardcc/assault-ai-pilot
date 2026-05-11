// =================================================
// Unit initializer helper
// Uses existing /api/units/{unit_key} API
// (same pattern as map pieces)
// =================================================

window.initializeUnitsFromScenario = async function (scenario) {

  if (!scenario || !Array.isArray(scenario.units)) {
    throw new Error("Scenario or scenario.units is invalid");
  }

  const units = {};

  for (const unit of scenario.units) {

    // ---------------------------------------------
    // Fetch unit definition from backend API
    // ---------------------------------------------
    const response = await fetch(
      `http://127.0.0.1:8000/api/units/${unit.unit_key}`
    );

    if (!response.ok) {
      throw new Error(
        "Failed to load unit definition: " + unit.unit_key
      );
    }

    const def = await response.json();
    const maxStrength = def.max_strength;

    units[unit.unit_id] = {
      unit_id: unit.unit_id,
      side: unit.side,
      unit_key: unit.unit_key,

      position: {
        q: unit.position.q,
        r: unit.position.r
      },

      // ✅ from backend definition
      max_strength: maxStrength,

      // ✅ live state (starts full)
      hp: maxStrength
    };
  }

  return units;
};