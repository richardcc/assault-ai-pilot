// -------------------------------------------------
// Sidebar Units Renderer
// -------------------------------------------------
// Renders unit cards in the left sidebar
// Uses data provided by app_pixi.js
// -------------------------------------------------

function renderUnitSidebar(units) {
  const sidebar = document.getElementById("sidebar-units");
  if (!sidebar) return;

  sidebar.innerHTML = "";

  const sides = [
    { id: "US", label: "Allies", icon: "🔴" },
    { id: "GE", label: "Axis", icon: "🔵" }
  ];

  sides.forEach(side => {
    const block = document.createElement("div");
    block.className = "side-block side-" + side.id;

    const title = document.createElement("h3");
    title.textContent = side.label;
    block.appendChild(title);

    units
      .filter(u => u.side === side.id)
      .forEach(unit => {
        block.appendChild(renderUnitCard(unit, side.icon));
      });

    sidebar.appendChild(block);
  });
}

// -------------------------------------------------
// Helpers
// -------------------------------------------------
function hexToBoardCoord(q, r) {
  const letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
  const col = letters[q] || "?";
  const row = typeof r === "number" ? r + 1 : "?";
  return `${col}${row}`;
}

// -------------------------------------------------
// Unit card renderer
// -------------------------------------------------
function renderUnitCard(unit, sideIcon) {
  // No renderizar unidades eliminadas
  if (unit.status && unit.status.includes("KIA")) {
    return document.createDocumentFragment();
  }

  const card = document.createElement("div");
  card.className = "unit-card";

  // Counter image
  const img = document.createElement("img");
  img.src = unit.image;
  img.className = "unit-counter";
  card.appendChild(img);

  // Info container
  const info = document.createElement("div");
  info.className = "unit-info";

  // Name + ID
  const name = document.createElement("div");
  name.className = "unit-name";
  name.textContent = `${sideIcon} ${unit.id}`;
  info.appendChild(name);

  // HP as hearts
  const hpRow = document.createElement("div");
  hpRow.className = "unit-hp";
  const hp = Math.max(0, unit.hp ?? 0);
  hpRow.textContent = "❤️".repeat(hp);
  info.appendChild(hpRow);

  // Position
  const posRow = document.createElement("div");
  posRow.className = "unit-pos";
  posRow.textContent =
    typeof unit.q === "number" && typeof unit.r === "number"
      ? `Pos: ${hexToBoardCoord(unit.q, unit.r)}`
      : "Pos: OFF MAP";
  info.appendChild(posRow);

  // Status
  if (unit.status && unit.status.length > 0) {
    const statusRow = document.createElement("div");
    statusRow.className = "unit-status";
    statusRow.textContent = unit.status.join(", ");
    info.appendChild(statusRow);
  }

  card.appendChild(info);
  return card;
}

// -------------------------------------------------
// ✅ EXPOSE GLOBALLY
// -------------------------------------------------
window.renderUnitSidebar = renderUnitSidebar;