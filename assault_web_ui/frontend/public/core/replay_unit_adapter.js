// =================================================
// Unit initializer helper
// Builds GAME_STATE.units from scenario-like data
// =================================================

window.initializeUnitsFromScenario = async function (scenario) {
  if (!scenario || !Array.isArray(scenario.units)) {
    console.error("[UNIT INIT] Scenario or scenario.units is invalid");
    return {};
  }

  const units = {};

  for (const unit of scenario.units) {

    // ---------------------------------------------
    // ✅ POSITION COMES AS OBJECT { q, r }
    // ---------------------------------------------
    const pos = unit.position;
    if (
      !pos ||
      typeof pos.q !== "number" ||
      typeof pos.r !== "number"
    ) {
      console.error(
        "[UNIT INIT] Invalid position format:",
        unit.unit_id,
        unit.position
      );
      continue;
    }

    const { q, r } = pos;

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

    // ---------------------------------------------
    // ✅ LIFE DATA (prefer replay, fallback to def)
    // ---------------------------------------------
    const maxHp =
      unit.max_hp ??
      def.max_strength ??
      1;

    const hp =
      unit.hp ?? maxHp;

    // ---------------------------------------------
    // Build GAME_STATE unit
    // ---------------------------------------------
    units[unit.unit_id] = {
      unit_id: unit.unit_id,
      side: unit.side,
      unit_key: unit.unit_key,

      // ✅ POSITION NORMALISED
      position: { q, r },

      // ✅ LIFE PRESERVED
      hp,
      max_hp: maxHp
    };
  }

  return units;
};