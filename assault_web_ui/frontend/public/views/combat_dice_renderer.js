// -------------------------------------------------
// Dice sprite mapping (semantic → actual PNG)
// -------------------------------------------------
const DICE_SPRITE_MAP = {
  BLUE: {
    "": "blue_01.png",
    "DAMAGE": "blue_02.png"
  },
  GREEN: {
    "": "green_01.png",
    "DAMAGE": "green_02.png",
    "CRITICAL+DAMAGE": "green_03.png"
  },
  RED: {
    "": "red_02.png",
    "DAMAGE": "red_01.png",
    "DAMAGE+DAMAGE": "red_03.png",
    "CRITICAL+DAMAGE": "red_04.png"
  },
  YELLOW: {
    "": "yellow_01.png",
    "DAMAGE": "yellow_02.png",
    "DAMAGE+DAMAGE": "yellow_03.png",
    "CRITICAL+DAMAGE": "yellow_04.png"
  }
};

// -------------------------------------------------
// Helpers
// -------------------------------------------------
function normalizeFaces(faces) {
  if (!faces || faces.length === 0) return "";
  return faces
    .map(f => (f === "SUPPRESS" ? "CRITICAL" : f))
    .sort()
    .join("+");
}

// -------------------------------------------------
// Single die renderer (✅ REAL HTML)
// -------------------------------------------------
function renderDie(die) {
  const key = normalizeFaces(die.faces);
  const file = DICE_SPRITE_MAP[die.color]?.[key];

  if (!file) {
    console.warn("Missing dice sprite:", die.color, key);
    return "";
  }

  return `
    <img
      src="/public/assets/dice/${file}"
      class="combat-die"
      alt="${die.color} ${key || "BLANK"}"
    />
  `;
}

// -------------------------------------------------
// Dice row renderer
// -------------------------------------------------
function renderDiceRow(label, dice) {
  if (!dice || dice.length === 0) return "";

  return `
    <div class="combat-row">
      ${label ? `<div class="combat-row-label">${label}</div>` : ""}
      <div class="combat-row-dice">
        ${dice.map(renderDie).join("")}
      </div>
    </div>
  `;
}

// ✅ Expose globally
window.renderDiceRow = renderDiceRow;
