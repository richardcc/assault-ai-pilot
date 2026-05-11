// =================================================
// Unit initializer helper
// Combines scenario placement + backend stats
// =================================================

window.initializeUnitsFromScenario = async function (scenario) {

  if (!scenario || !Array.isArray(scenario.units)) {
    console.error("Scenario or scenario.units is invalid");
    return {};
  }

  const units = {};

  for (const unit of scenario.units) {

    // ---------------------------------------------
    // ✅ POSITION COMES AS ARRAY [q, r]
    // ---------------------------------------------
    if (
      !Array.isArray(unit.position) ||
      unit.position.length !== 2 ||
      typeof unit.position[0] !== "number" ||
      typeof unit.position[1] !== "number"
    ) {
      console.error(
        "[UNIT INIT] Invalid position format:",
        unit.unit_id,
        unit.position
      );
      continue;
    }

    const [q, r] = unit.position;

    // ---------------------------------------------
    // Fetch unit definition from backend API
    // ---------------------------------------------
    let def;
    try {
      const response = await fetch(
        `http://127.0.0.1:8000/api/units/${unit.unit_key}`
      );
      def = await response.json();
    } catch (e) {
      console.error(
        "[UNIT INIT] Failed to fetch unit definition:",
        unit.unit_key,
        e
      );
      continue;
    }

    const maxStrength = def.max_strength;

    // ---------------------------------------------
    // Build GAME_STATE unit
    // ---------------------------------------------
    units[unit.unit_id] = {
      unit_id: unit.unit_id,
      side: unit.side,
      unit_key: unit.unit_key,

      // ✅ POSITION NORMALISED
      position: { q, r },

      max_strength: maxStrength,
      hp: maxStrength
    };
  }

  return units;
};