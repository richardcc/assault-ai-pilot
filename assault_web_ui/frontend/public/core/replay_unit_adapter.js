// =================================================
// ADAPTER: Replay initial_state -> Scenario-like shape
// =================================================

window.adaptReplayInitialStateToScenario = function (replay) {
  if (!replay || !replay.initial_state) return null;

  return {
    units: replay.initial_state.units.map(u => ({
      unit_id: u.id,
      unit_key: u.type,        // maps replay "type" to backend key
      side: u.side,
      position: [u.q, u.r]
      // hp is handled later, not in scenario init
    }))
  };
};
