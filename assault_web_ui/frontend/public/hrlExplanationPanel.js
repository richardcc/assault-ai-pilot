// -------------------------------------------------
// HRL EXPLANATION PANEL
// Pure UI renderer – no game logic
// -------------------------------------------------

const hrlPanelEl = document.getElementById("hrl-explanation");

/**
 * Clear the HRL panel.
 */
function clearHRLExplanation() {
  if (!hrlPanelEl) return;
  hrlPanelEl.innerHTML = "<em>No strategic explanation available.</em>";
}

/**
 * Render HRL explanation for the current activation.
 *
 * @param {object|null} explanationResponse
 */
function renderHRLExplanation(explanationResponse) {
  console.log("HRL RESPONSE RECEIVED:", explanationResponse?.strategic_intent);

  if (
    !explanationResponse ||
    !explanationResponse.strategic_intent
  ) {
    clearHRLExplanation();
    return;
  }

  const strategic = explanationResponse.strategic_intent;
  const unitId = strategic.unit_id;

  const unitLabel = unitId
    ? `Unit <strong>${unitId}</strong>`
    : `<span class="hrl-warning">⚠ Unit missing</span>`;

  hrlPanelEl.innerHTML = `
    <div class="hrl-card">

      <div class="hrl-header">
        <span class="hrl-title">
          Strategic Intent — ${unitLabel}
        </span>
      </div>

      <div class="hrl-meta">
        <span class="hrl-option">${strategic.option}</span>
        <span class="hrl-category">${strategic.category}</span>
      </div>

      <div class="hrl-body">
        <p>${strategic.explanation}</p>
      </div>

    </div>
  `;
}

// Expose globally if not using modules
window.renderHRLExplanation = renderHRLExplanation;
window.clearHRLExplanation = clearHRLExplanation;