// =================================================
// REPLAY CURSOR UTILS
// Synchronizes TURN and STEP from replay cursor
// =================================================

window.updateTurnStepFromCursor = function updateTurnStepFromCursor(gameState) {
  const replay = gameState.replay;
  const cursor = gameState.replayCursor;
  if (!replay || !cursor) return;

  if (cursor.turnIndex === 0 && cursor.eventIndex === 0) {
    gameState.turn = replay.initial_state?.turn ?? 1;
    gameState.step = 0;
    return;
  }

  const turnData = replay.turns[cursor.turnIndex];
  if (!turnData) return;

  gameState.turn = turnData.turn;
  gameState.step = cursor.eventIndex + 1;
};