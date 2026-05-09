const DICE_COLOR_ICON = {
  RED: "🔴",
  YELLOW: "🟡",
  GREEN: "🟢",
  BLUE: "🔵"
};

const DICE_FACE_ICON = {
  CRITICAL: "💥",
  DAMAGE: "❤️",
  SUPPRESS: "😵"
};

const BLANK_ICON = "⚪";

function renderDie(die) {
  const color = DICE_COLOR_ICON[die.color] || "❓";

  if (!die.faces || die.faces.length === 0) {
    return color + BLANK_ICON;
  }

  const faces = die.faces
    .slice()
    .sort()
    .map(f => DICE_FACE_ICON[f] || "❓")
    .join("");

  return color + faces;
}

function renderDiceRow(label, dice) {
  if (!dice || dice.length === 0) return "";

  const rendered = dice.map(renderDie).join(" ");
  return `
    <div class="combat-row">
      <div class="combat-row-label">${label}</div>
      <div class="combat-row-dice">${rendered}</div>
    </div>
  `;
}