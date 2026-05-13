// -------------------------------------------------
// HRL EXPLANATION VIEW
// -------------------------------------------------

function clearHRLExplanation() {
  const el = document.getElementById("hrl-explanation");
  if (!el) return;

  el.innerHTML = `
    <div class="hrl-placeholder">
      <em>No strategic analysis available.</em>
    </div>
  `;
}


// -------------------------------------------------
function renderHRLExplanation(response) {
  const el = document.getElementById("hrl-explanation");
  if (!el) return;

  // ✅ REAL ACTION (from replay)
  const real = window.lastRealText || "Unknown action";

  // ✅ AI recommendation (from backend)
  const aiOption = response?.strategic_intent?.option || "UNKNOWN";

  // ✅ Backend reasoning (NO inventado)
  const aiExplanation = response?.strategic_intent?.explanation || "";

  el.innerHTML = `
    <div class="hrl-card">

      <div class="hrl-title">
        Strategic Analysis
      </div>

      <div class="hrl-section">
        <div class="hrl-label">
          Real action
        </div>
        <div class="hrl-text">
          ${real}
        </div>
      </div>

      <div class="hrl-section">
        <div class="hrl-label">
          AI recommendation
        </div>
        <div class="hrl-text">
          <strong>${aiOption}</strong>
        </div>
      </div>

      <div class="hrl-section">
        <div class="hrl-label">
          Reasoning
        </div>
        <div class="hrl-text">
          ${aiExplanation}
        </div>
      </div>

      <div class="hrl-actions">
        <button id="explain-btn">Explain decision</button>
      </div>

    </div>
  `;
}


// -------------------------------------------------
function updateHRLExplanation(response) {
  renderHRLExplanation(response);
}


// -------------------------------------------------
// ✅ GLOBAL API (MUY IMPORTANTE)
// -------------------------------------------------
window.renderHRLExplanation = renderHRLExplanation;
window.clearHRLExplanation = clearHRLExplanation;
window.updateHRLExplanation = updateHRLExplanation;