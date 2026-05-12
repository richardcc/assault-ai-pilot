// =================================================
// REPLAY NAVIGATION
// Handles cursor movement only (no rendering)
// =================================================

window.nextStep = function nextStep(gameState) {
  const replay = gameState.replay;
  const cursor = gameState.replayCursor;
  if (!replay) return;

  const currentTurn = replay.turns[cursor.turnIndex];
  if (!currentTurn) return;

  // Advance within the same turn
  if (cursor.eventIndex + 1 < currentTurn.events.length) {
    cursor.eventIndex++;
  }
  // Move to next turn
  else if (cursor.turnIndex + 1 < replay.turns.length) {
    cursor.turnIndex++;
    cursor.eventIndex = 0;
  }

  updateTurnStepFromCursor(gameState);
};


// ---------------------------------------------
// Step backwards (REBUILD state)
// ---------------------------------------------
window.prevStep = function prevStep(gameState) {
  const replay = gameState.replay;
  const cursor = gameState.replayCursor;
  if (!replay) return;

  // Move back within the same turn
  if (cursor.eventIndex > 0) {
    cursor.eventIndex--;
  }
  // Move to previous turn
  else if (cursor.turnIndex > 0) {
    cursor.turnIndex--;
    const prevTurn = replay.turns[cursor.turnIndex];
    cursor.eventIndex = prevTurn.events.length - 1;
  } else {
    return;
  }

  updateTurnStepFromCursor(gameState);
  rebuildStateUpToCursor(gameState);
};


// ---------------------------------------------
// Turn backwards (REBUILD state)
// ---------------------------------------------
window.prevTurn = function prevTurn(gameState) {
  const cursor = gameState.replayCursor;
  if (cursor.turnIndex === 0) return;

  cursor.turnIndex--;
  cursor.eventIndex = 0;

  updateTurnStepFromCursor(gameState);
  rebuildStateUpToCursor(gameState);
};


// ---------------------------------------------
// Turn forwards (REBUILD to end of turn)
// ---------------------------------------------
window.nextTurn = function nextTurn(gameState) {
  const replay = gameState.replay;
  const cursor = gameState.replayCursor;
  if (!replay) return;

  if (cursor.turnIndex + 1 >= replay.turns.length) return;

  cursor.turnIndex++;
  cursor.eventIndex = replay.turns[cursor.turnIndex].events.length - 1;

  updateTurnStepFromCursor(gameState);
  rebuildStateUpToCursor(gameState);
};
