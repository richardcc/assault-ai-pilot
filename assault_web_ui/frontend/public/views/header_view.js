// =================================================
// HEADER VIEW (Scenario header)
// =================================================

window.renderHeaderView = function renderHeaderView(gameState) {

  const replay = gameState.replay;
  const uiMetadata = gameState.uiMetadata;

  return {
    left(container) {
    const replay = gameState.replay;
    const uiMetadata = gameState.uiMetadata;

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

    center(container) {
      const turn = gameState.turn;
      const step = gameState.step;

      container.innerHTML = `
        <div class="header-center">
          <div>Turn: ${turn}</div>
          <div>Step: ${step}</div>
        </div>
      `;
    },

    right(container) {
      container.innerHTML = `
        <div class="header-right">
          Replay mode
        </div>
      `;
    }
  };
};