// -------------------------------------------------
// Header Renderer
// -------------------------------------------------
// Renders scenario info, sides, turn/step AND controls
// -------------------------------------------------

function renderHeader({
  scenario,
  turn,
  step,
  totalTurns,
  totalSteps
}) {
  const root = document.getElementById("header-root");
  if (!root) return;

  const scenarioName = scenario?.name ?? "Unknown Scenario";

  const usLabel  = scenario?.sides?.US?.label   ?? "US";
  const usPlayer = scenario?.sides?.US?.player  ?? "Player 1";

  const geLabel  = scenario?.sides?.GE?.label   ?? "GE";
  const gePlayer = scenario?.sides?.GE?.player  ?? "Player 2";

  root.innerHTML = `
    <div class="header-content">

      <div class="header-top header-layout">
        <div class="header-left box">
          <div class="scenario-name">${scenarioName}</div>

          <div class="scenario-sides">
            <div class="side">
              <span>${usLabel}</span>
              <span>${usPlayer}</span>
            </div>

            <div class="vs">vs</div>

            <div class="side">
              <span>${geLabel}</span>
              <span>${gePlayer}</span>
            </div>
          </div>
        </div>

        <div class="header-center box">
          TURN ${turn} / ${totalTurns}
          &nbsp;·&nbsp;
          STEP ${step} / ${totalSteps}
        </div>
      </div>

      <div class="header-controls">
        <button id="btn-prev-turn">⏮ Prev Turn</button>
        <button id="btn-next-turn">Next Turn ⏭</button>
        <button id="btn-prev-step">◀ Prev Step</button>
        <button id="btn-next-step">Next Step ▶</button>
      </div>

    </div>
  `;
}

// -------------------------------------------------
// Public API
// -------------------------------------------------
window.renderHeader = renderHeader;
