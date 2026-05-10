// -------------------------------------------------
// Header Renderer
// -------------------------------------------------
// Renders scenario info, sides, turn/step AND controls
// Supports scenario sides AND replay meta sides
// -------------------------------------------------

function renderHeader({
  scenario,
  replay,          // ✅ NUEVO (opcional)
  turn,
  step,
  totalTurns,
  totalSteps
}) {
  const root = document.getElementById("header-root");
  if (!root) return;

  // -------------------------------------------------
  // Scenario name
  // -------------------------------------------------
  const scenarioName =
    replay?.meta?.scenario_id ??
    scenario?.name ??
    "Unknown Scenario";

  // -------------------------------------------------
  // Resolve side controllers
  // Priority:
  // 1) replay.meta.sides (grabado)
  // 2) scenario.sides   (legacy)
  // -------------------------------------------------
  const sidesFromReplay = replay?.meta?.sides;
  const sidesFromScenario = scenario?.sides;

  function controllerLabel(v) {
    if (!v) return "Unknown";
    if (v === "RL") return "🧠 RL";
    if (v === "HEURISTIC") return "📜 Heuristic";
    if (v === "HUMAN") return "👤 Human";
    return v;
  }

  // US
  const usLabel =
    sidesFromScenario?.US?.label ??
    "US";

  const usController =
    sidesFromReplay?.US ??
    sidesFromScenario?.US?.player ??
    "Unknown";

  // GE
  const geLabel =
    sidesFromScenario?.GE?.label ??
    "GE";

  const geController =
    sidesFromReplay?.GE ??
    sidesFromScenario?.GE?.player ??
    "Unknown";

  // -------------------------------------------------
  // Render
  // -------------------------------------------------
  root.innerHTML = `
    <div class="header-content">

      <div class="header-top header-layout">
        <div class="header-left box">
          <div class="scenario-name">${scenarioName}</div>

          <div class="scenario-sides">
            <div class="side">
              <span>${usLabel}</span>
              <span>${controllerLabel(usController)}</span>
            </div>

            <div class="vs">vs</div>

            <div class="side">
              <span>${geLabel}</span>
              <span>${controllerLabel(geController)}</span>
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
        <button id="btn-prev-step">◀ Prev Step</button>
        <button id="btn-next-step">Next Step ▶</button>
        <button id="btn-next-turn">Next Turn ⏭</button>
      </div>

    </div>
  `;
}

// -------------------------------------------------
// Public API
// -------------------------------------------------
window.renderHeader = renderHeader;