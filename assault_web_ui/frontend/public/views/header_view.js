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
              <img src="${sideA.marker}"
                   class="header-marker"
                   alt="${sideA.short_label}" />
              <div class="header-player-text">
                <div class="header-player-side">${sideA.label}</div>
                <div class="header-player-controller">${ctrlA.label}</div>
              </div>
            </div>

            <div class="header-vs-text">VS</div>

            <div class="header-player">
              <img src="${sideB.marker}"
                   class="header-marker"
                   alt="${sideB.short_label}" />
              <div class="header-player-text">
                <div class="header-player-side">${sideB.label}</div>
                <div class="header-player-controller">${ctrlB.label}</div>
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
    // RIGHT: Replay buttons (temporal)
    // ---------------------------------------------
    // ---------------------------------------------
    // RIGHT: Replay buttons (Step + Turn)
    // ---------------------------------------------
    right(container) {
      container.innerHTML = `
        <div class="header-replay-controls">

          <!-- PREVIOUS TURN -->
          <button
            class="replay-btn"
            title="Previous Turn"
            onclick="
              prevTurn(GAME_STATE);
              renderFrame(GAME_STATE, UI_STATE);
            ">
            ⏮
          </button>

          <!-- PREVIOUS STEP -->
          <button
            class="replay-btn"
            title="Previous Step"
            onclick="
              prevStep(GAME_STATE);
              renderFrame(GAME_STATE, UI_STATE);
            ">
            ◀
          </button>

          <!-- NEXT STEP -->
          <button
            class="replay-btn primary"
            title="Next Step"
            onclick="
              nextStep(GAME_STATE);
              applyReplayEvent(GAME_STATE);
              renderFrame(GAME_STATE, UI_STATE);
            ">
            ▶
          </button>

          <!-- NEXT TURN -->
          <button
            class="replay-btn"
            title="Next Turn"
            onclick="
              nextTurn(GAME_STATE);
              renderFrame(GAME_STATE, UI_STATE);
            ">
            ⏭
          </button>

        </div>
      `;
    }
  };
};
