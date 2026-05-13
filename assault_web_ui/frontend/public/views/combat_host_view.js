window.renderCombatHostView = function renderCombatHostView(container) {
  let panel = container.querySelector("#combat-panel");
  if (!panel) {
    panel = document.createElement("div");
    panel.id = "combat-panel";
    panel.className = "combat-panel";
    container.appendChild(panel);
  }
};
