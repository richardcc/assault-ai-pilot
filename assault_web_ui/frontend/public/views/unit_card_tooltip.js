// =================================================
// UNIT CARD TOOLTIP (GLOBAL OVERLAY)
// =================================================

(function () {

  const OFFSET = 16;

  const tooltip = document.createElement("div");
  tooltip.className = "unit-card-tooltip";
  tooltip.style.display = "none";

  const overlayRoot = document.getElementById("overlay-root");
  if (!overlayRoot) {
    console.error("[unit_card_tooltip] overlay-root not found");
    return;
  }

  overlayRoot.appendChild(tooltip);

  function positionTooltip(evt) {
    const rect = tooltip.getBoundingClientRect();

    let x = evt.clientX + OFFSET;
    let y = evt.clientY + OFFSET;

    // Clamp right
    if (x + rect.width > window.innerWidth) {
      x = evt.clientX - rect.width - OFFSET;
    }

    // Clamp bottom
    if (y + rect.height > window.innerHeight) {
      y = evt.clientY - rect.height - OFFSET;
    }

    tooltip.style.left = x + "px";
    tooltip.style.top  = y + "px";
  }

  // -----------------------------------------------
  // SHOW
  // -----------------------------------------------
  window.showUnitTooltip = function (unit, uiMetadata, evt) {
    const def = uiMetadata?.units?.[unit.unit_key];
    if (!def || !def.card) return;

    tooltip.innerHTML = `
      <img src="/public/art/unit_cards/${def.card}" alt="${def.label}">
    `;

    tooltip.style.display = "block";
    positionTooltip(evt);
  };

  // -----------------------------------------------
  // MOVE
  // -----------------------------------------------
  window.moveUnitTooltip = function (evt) {
    positionTooltip(evt);
  };

  // -----------------------------------------------
  // HIDE
  // -----------------------------------------------
  window.hideUnitTooltip = function () {
    tooltip.style.display = "none";
  };

})();