// -------------------------------------------------
// TACTICAL EXPLANATION PANEL
// Pure UI renderer – no game or rules logic
// -------------------------------------------------

const tacticalPanelEl = document.getElementById("tactical-explanation");

/**
 * Clear the tactical explanation panel.
 */
function clearTacticalExplanation() {
  if (!tacticalPanelEl) return;
  tacticalPanelEl.innerHTML = "<em>No tactical explanation available.</em>";
}

/**
 * Render tactical explanation for the current activation.
 *
 * @param {object|null} explanationResponse
 */
function renderTacticalExplanation(explanationResponse) {
  if (
    !explanationResponse ||
    !explanationResponse.tactical_execution
  ) {
    clearTacticalExplanation();
    return;
  }

  const tactical = explanationResponse.tactical_execution;

  tacticalPanelEl.innerHTML = `
    <div class="tactical-card">
      <div class="tactical-title">Tactical Resolution</div>

      <p><strong>What happened:</strong> ${tactical.facts}</p>
      <p><strong>Why it happened:</strong> ${tactical.rules}</p>
    </div>
  `;
}

// Expose globally
window.renderTacticalExplanation = renderTacticalExplanation;
window.clearTacticalExplanation = clearTacticalExplanation;