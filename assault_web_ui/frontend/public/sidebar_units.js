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
    { id: "US", label: "Allies" },
    { id: "GE", label: "Axis" }
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
        block.appendChild(renderUnitCard(unit));
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
function renderUnitCard(unit) {
  const card = document.createElement("div");
  card.className = "unit-card";

  // Counter image
  const img = document.createElement("img");
  img.src = unit.image;
  img.className = "unit-counter";

  // Info
  const info = document.createElement("div");
  info.className = "unit-info";

  const positionText =
    typeof unit.q === "number" && typeof unit.r === "number"
      ? `Pos: ${hexToBoardCoord(unit.q, unit.r)}`
      : "Pos: OFF MAP";

  info.innerHTML = `
    <strong>${unit.name}</strong><br>
    <small>ID: ${unit.id}</small><br>
    HP: ${unit.hp} · Steps: ${unit.steps}<br>
    ${positionText}<br>
    <em>${unit.status.join(", ")}</em>
  `;

  card.appendChild(img);
  card.appendChild(info);

  return card;
}

// -------------------------------------------------
// ✅ EXPOSE GLOBALLY
// -------------------------------------------------
window.renderUnitSidebar = renderUnitSidebar;