// =================================================
// COMBAT PANEL VIEW
// Shows combat resolution HTML (pure UI)
// =================================================

window.showCombatPanel = function showCombatPanel(html) {
  const container = document.getElementById("combat-panel");
  if (!container) return;

  container.innerHTML = html;
  container.style.display = "block";
};

window.hideCombatPanel = function hideCombatPanel() {
  const container = document.getElementById("combat-panel");
  if (!container) return;

  container.innerHTML = "";
  container.style.display = "none";
};