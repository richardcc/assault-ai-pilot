// =================================================
// REPLAY EVENT APPLIER
// - applySingleEvent: pure, deterministic
// - applyReplayEvent: wrapper using replayCursor
// =================================================


// ---------------------------------------------
// Apply ONE event object (pure, no cursor logic)
// ---------------------------------------------
window.applySingleEvent = function applySingleEvent(gameState, event) {
  if (!event) return;

  switch (event.type) {

    case "UNIT_MOVED": {
      const { unit_id, to } = event.payload;
      const unit = gameState.units[unit_id];
      if (!unit || !unit.position) return;

      unit.position.q = to.q;
      unit.position.r = to.r;
      break;
    }

    case "ACTION_EFFECT": {
      const p = event.payload;

      // Defender killed
      if (p.defender_killed) {
        const unit = gameState.units[p.defender];
        if (unit) {
          unit.alive = false;
          unit.hp = 0;
        }
        break;
      }

      // HP change (non-lethal)
      if (typeof p.defender_hp_after === "number") {
        const unit = gameState.units[p.defender];
        if (unit) {
          unit.hp = p.defender_hp_after;
        }
      }
      break;
    }

    // ACTION events do not mutate state directly
  }
};


// ---------------------------------------------
// Apply event at current replayCursor (forward)
// ---------------------------------------------
window.applyReplayEvent = function applyReplayEvent(gameState) {
  const replay = gameState.replay;
  const cursor = gameState.replayCursor;
  if (!replay) return;

  const turn = replay.turns[cursor.turnIndex];
  if (!turn) return;

  const event = turn.events[cursor.eventIndex];
  if (!event) return;

  applySingleEvent(gameState, event);
};