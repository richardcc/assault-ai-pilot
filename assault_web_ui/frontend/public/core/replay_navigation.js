// =================================================
// REPLAY NAVIGATION
// Cursor moves by ACTION groups (not raw events)
// =================================================


// -------------------------------------------------
// Compute ACTION block forward
// Returns { from, to } event indices
// -------------------------------------------------
function computeNextActionRange(replay, turnIndex, eventIndex) {
  const turn = replay.turns[turnIndex];
  if (!turn) return null;

  // Find start (must be ACTION)
  let from = eventIndex;

  // If cursor is not on ACTION, move forward to next ACTION
  if (turn.events[from]?.type !== "ACTION") {
    while (from < turn.events.length && turn.events[from]?.type !== "ACTION") {
      from++;
    }
  }

  if (from >= turn.events.length) return null;

  // Consume until next ACTION
  let to = from + 1;
  while (to < turn.events.length && turn.events[to]?.type !== "ACTION") {
    to++;
  }

  return { from, to };
}


// -------------------------------------------------
// Advance one ACTION (forward)
// Returns consumed range for application
// -------------------------------------------------
window.nextStep = function nextStep(gameState) {
  const replay = gameState.replay;
  const cursor = gameState.replayCursor;
  if (!replay) return null;

  const range = computeNextActionRange(
    replay,
    cursor.turnIndex,
    cursor.eventIndex
  );

  if (!range) return null;

  // Advance cursor
  cursor.eventIndex = range.to;

  // End of turn → next turn
  const turn = replay.turns[cursor.turnIndex];
  if (cursor.eventIndex >= turn.events.length) {
    if (cursor.turnIndex + 1 < replay.turns.length) {
      cursor.turnIndex++;
      cursor.eventIndex = 0;
    }
  }

  updateTurnStepFromCursor(gameState);
  return range; // ✅ CRITICAL
};



// -------------------------------------------------
// Go back one ACTION (backward) – rebuild
// -------------------------------------------------
window.prevStep = function prevStep(gameState) {
  const replay = gameState.replay;
  const cursor = gameState.replayCursor;
  if (!replay) return;

  let turnIndex = cursor.turnIndex;
  let eventIndex = cursor.eventIndex - 1;

  while (turnIndex >= 0) {
    const turn = replay.turns[turnIndex];
    if (!turn) return;

    if (eventIndex < 0) {
      turnIndex--;
      if (turnIndex < 0) return;
      eventIndex = replay.turns[turnIndex].events.length - 1;
      continue;
    }

    while (eventIndex >= 0 && turn.events[eventIndex]?.type !== "ACTION") {
      eventIndex--;
    }

    if (eventIndex >= 0) {
      cursor.turnIndex = turnIndex;
      cursor.eventIndex = eventIndex;
      break;
    }

    turnIndex--;
    if (turnIndex >= 0) {
      eventIndex = replay.turns[turnIndex].events.length - 1;
    }
  }

  updateTurnStepFromCursor(gameState);
  rebuildStateUpToCursor(gameState);
};


// -------------------------------------------------
// Turn backwards (REBUILD state)
// -------------------------------------------------
window.prevTurn = function prevTurn(gameState) {
  const cursor = gameState.replayCursor;
  if (cursor.turnIndex === 0) return;

  cursor.turnIndex--;
  cursor.eventIndex = 0;

  updateTurnStepFromCursor(gameState);
  rebuildStateUpToCursor(gameState);
};


// -------------------------------------------------
// Turn forwards (REBUILD to end of turn)
// -------------------------------------------------
window.nextTurn = function nextTurn(gameState) {
  const replay = gameState.replay;
  const cursor = gameState.replayCursor;
  if (!replay) return;

  if (cursor.turnIndex + 1 >= replay.turns.length) return;

  cursor.turnIndex++;
  cursor.eventIndex = 0; // ✅ start of turn

  updateTurnStepFromCursor(gameState);
  rebuildStateUpToCursor(gameState);
};
