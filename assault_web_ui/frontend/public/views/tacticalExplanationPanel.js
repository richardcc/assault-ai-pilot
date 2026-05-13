// -------------------------------------------------
// TACTICAL EXPLANATION VIEW
// Pure UI renderer – no game or rules logic
// -------------------------------------------------

function clearTacticalExplanation() {
  const el = document.getElementById("tactical-explanation");
  if (!el) return;

  el.innerHTML = `
    <div class="tactical-placeholder">
      <em>No tactical explanation available.</em>
    </div>
  `;
}


// ✅ optional: simplificar texto (UX PRO)
function cleanText(text) {
  if (!text) return "";

  return text
    .replace(/according to .*rules/i, "")
    .replace(/\s+/g, " ")
    .trim();
}


// -------------------------------------------------
function renderTacticalExplanation(explanationResponse) {

  const el = document.getElementById("tactical-explanation");
  if (!el) return;

  if (
    !explanationResponse ||
    !explanationResponse.tactical_execution
  ) {
    clearTacticalExplanation();
    return;
  }

  const tactical = explanationResponse.tactical_execution;

  const facts = cleanText(tactical.facts || "No facts available.");
  const rules = cleanText(tactical.rules || "No rules explanation available.");
  const result = tactical.result || "UNKNOWN";

  el.innerHTML = `
    <div class="tactical-card">

      <div class="tactical-title">
        Tactical Resolution
      </div>

      <div class="tactical-section">
        <div class="tactical-label">What happened</div>
        <div class="tactical-text">${facts}</div>
      </div>

      <div class="tactical-section">
        <div class="tactical-label">Why it happened</div>
        <div class="tactical-text">${rules}</div>
      </div>

      <div class="tactical-result">
        ${result}
      </div>

    </div>
  `;
}


// -------------------------------------------------
function updateTacticalExplanation(explanationResponse) {
  renderTacticalExplanation(explanationResponse);
}

// -------------------------------------------------
window.renderTacticalExplanation = renderTacticalExplanation;
window.clearTacticalExplanation = clearTacticalExplanation;
window.updateTacticalExplanation = updateTacticalExplanation;
