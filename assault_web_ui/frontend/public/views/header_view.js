// =================================================
// HEADER VIEW (Scenario header + Replay controls)
// =================================================

window.renderHeaderView = function renderHeaderView(gameState) {

  const replay = gameState.replay;
  const uiMetadata = gameState.uiMetadata;

  return {

    // ---------------------------------------------
    // LEFT: Scenario + VS players
    // ---------------------------------------------
    left(container) {

      if (!replay || !uiMetadata || GAME_STATE.players.length !== 2) {
        container.innerHTML = "<em>No scenario loaded</em>";
        return;
      }

      const scenarioId = replay.meta.scenario_id;
      const [playerA, playerB] = GAME_STATE.players;

      const sideA = uiMetadata.sides[playerA.sideId];
      const ctrlA = uiMetadata.controllers[playerA.controllerId];
      const sideB = uiMetadata.sides[playerB.sideId];
      const ctrlB = uiMetadata.controllers[playerB.controllerId];

      container.innerHTML = `
        <div class="header-scenario">
          <div class="header-scenario-id">
            Scenario: ${scenarioId}
          </div>

          <div class="header-vs-row">
            <div class="header-player">
              <img src="${sideA.marker}" class="header-marker" />
              <div class="header-player-text">
                <div>${sideA.label}</div>
                <div>${ctrlA.label}</div>
              </div>
            </div>

            <div class="header-vs-text">VS</div>

            <div class="header-player">
              <img src="${sideB.marker}" class="header-marker" />
              <div class="header-player-text">
                <div>${sideB.label}</div>
                <div>${ctrlB.label}</div>
              </div>
            </div>
          </div>
        </div>
      `;
    },

    // ---------------------------------------------
    // CENTER: Turn / Step
    // ---------------------------------------------
    center(container) {
      container.innerHTML = `
        <div class="header-center">
          <div>Turn: ${gameState.turn}</div>
          <div>Step: ${gameState.step}</div>
        </div>
      `;
    },

    // ---------------------------------------------
    // RIGHT: Replay controls
    // ---------------------------------------------
    // ---------------------------------------------
    // RIGHT: Replay controls
    // ---------------------------------------------
    right(container) {
      container.innerHTML = `
        <div class="header-replay-controls">

          <!-- PREVIOUS TURN -->
          <button class="replay-btn"
            title="Previous Turn"
            onclick="
              delete GAME_STATE.__renderMode;
              prevTurn(GAME_STATE);
              rebuildStateUpToCursor(GAME_STATE);
              worldRenderer.updateUnits(GAME_STATE);
              renderFrame(GAME_STATE, UI_STATE);
            ">
            ⏮
          </button>

          <!-- PREVIOUS STEP -->
          <button class="replay-btn"
            title="Previous Step"
            onclick="
              delete GAME_STATE.__renderMode;
              prevStep(GAME_STATE);
              worldRenderer.updateUnits(GAME_STATE);
              renderFrame(GAME_STATE, UI_STATE);
            ">
            ◀
          </button>

          <!-- NEXT STEP (ACTION-BASED, ANIMATED) -->
          <button class="replay-btn primary"
            title="Next Step"
            onclick="
              GAME_STATE.__renderMode = 'incremental';

              const range = nextStep(GAME_STATE);
              if (range) {
                applyEventRange(
                  GAME_STATE,
                  GAME_STATE.replayCursor.turnIndex,
                  range.from,
                  range.to
                );
              }

              worldRenderer.updateUnits(GAME_STATE);
              renderFrame(GAME_STATE, UI_STATE);
            ">
            ▶
          </button>

          <!-- NEXT TURN -->
          <button class="replay-btn"
            title="Next Turn"
            onclick="
              delete GAME_STATE.__renderMode;
              nextTurn(GAME_STATE);
              rebuildStateUpToCursor(GAME_STATE);
              worldRenderer.updateUnits(GAME_STATE);
              renderFrame(GAME_STATE, UI_STATE);
            ">
            ⏭
          </button>

        </div>
      `;
    }
  };
};