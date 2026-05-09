function renderUnitSidebar(units) {
  const sidebar = document.getElementById("sidebar-units");
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

function renderUnitCard(unit) {
  const card = document.createElement("div");
  card.className = "unit-card";

  const img = document.createElement("img");
  img.src = unit.image;
  img.className = "unit-counter";

  const info = document.createElement("div");
  info.className = "unit-info";
  info.innerHTML = `
    <strong>${unit.name}</strong><br/>
    STR ${unit.strength} · Steps ${unit.steps}<br/>
    ${unit.status.join(", ")}
  `;

  card.appendChild(img);
  card.appendChild(info);

  return card;
}