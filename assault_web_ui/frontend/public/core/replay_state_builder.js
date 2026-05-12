// =================================================
// REPLAY STATE BUILDER
// Rebuilds GAME_STATE from replay.initial_state
// up to the current replayCursor
// =================================================

window.rebuildStateUpToCursor = function rebuildStateUpToCursor(gameState) {
  const replay = gameState.replay;
  if (!replay) return;

  // ---------------------------------------------
  // 1. Reset units to initial_state
  // ---------------------------------------------
  gameState.units = {};

  for (const u of replay.initial_state.units) {
    gameState.units[u.id] = {
      unit_id: u.id,
      side: u.side,
      unit_key: u.type,
      hp: u.hp,
      position: { q: u.q, r: u.r },
      alive: true,
      suppressed: false
    };
  }

  // ---------------------------------------------
  // 2. Reapply events deterministically
  // ---------------------------------------------
  for (let t = 0; t <= gameState.replayCursor.turnIndex; t++) {
    const turn = replay.turns[t];
    if (!turn) continue;

    const maxEvent =
      t === gameState.replayCursor.turnIndex
        ? gameState.replayCursor.eventIndex
        : turn.events.length;

    for (let e = 0; e < maxEvent; e++) {
      applySingleEvent(gameState, turn.events[e]);
    }
  }
};
