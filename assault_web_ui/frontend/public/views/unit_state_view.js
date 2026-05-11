// =================================================
// UNIT STATE VIEW (Columns by side, horizontal scroll)
// =================================================

window.renderUnitStateView = function renderUnitStateView(gameState) {

  return {
    render(container) {

      const unitsState = gameState.units;
      const unitDefs = gameState.uiMetadata?.units;

      if (!unitsState || Object.keys(unitsState).length === 0) {
        container.innerHTML = "<em>No units</em>";
        return;
      }

      // Reset container
      container.innerHTML = "";

      // -------------------------------------------------
      // Group units by side (FROM GAME_STATE.units)
      // -------------------------------------------------
      const unitsBySide = {};

      Object.values(unitsState).forEach(unit => {
        if (!unitsBySide[unit.side]) {
          unitsBySide[unit.side] = [];
        }
        unitsBySide[unit.side].push(unit);
      });

      // -------------------------------------------------
      // Render one column per side
      // -------------------------------------------------
      Object.entries(unitsBySide).forEach(([side, units]) => {

        // Side column
        const sideBlock = document.createElement("div");
        sideBlock.className = "unit-state-side";

        // Side header
        const header = document.createElement("div");
        header.className = "unit-state-side-header";
        header.textContent = side;
        sideBlock.appendChild(header);

        // Horizontal scroll container
        const scroll = document.createElement("div");
        scroll.className = "unit-state-scroll";

        // -------------------------------------------------
        // Unit cards
        // -------------------------------------------------
        units.forEach(unit => {

          const card = document.createElement("div");
          card.className = "unit-card";
          card.dataset.unitId = unit.unit_id;

          // ---------------------------------------------
          // Counter image
          // ---------------------------------------------
          const counter = document.createElement("div");
          counter.className = "unit-card-counter";

          const def = unitDefs?.[unit.unit_key];
          if (def && def.full) {
            const img = document.createElement("img");
            img.src = "/public/art/counters/" + def.full;
            img.alt = def.label ?? unit.unit_key;
            counter.appendChild(img);
          }

          // ---------------------------------------------
          // HP hearts (under counter)
          // ---------------------------------------------
          const hpBar = document.createElement("div");
          hpBar.className = "unit-card-hp";

          const hp = unit.hp ?? 0;
          const max = unit.max_strength ?? 0;

          for (let i = 0; i < max; i++) {
            const heart = document.createElement("span");
            heart.className = "unit-heart";
            heart.textContent = i < hp ? "❤️" : "🤍";
            hpBar.appendChild(heart);
          }

          // ---------------------------------------------
          // Label
          // ---------------------------------------------
          const name = document.createElement("div");
          name.className = "unit-card-name";
          name.textContent = def?.label ?? unit.unit_key;

          // ---------------------------------------------
          // HOVER → show large unit card
          // ---------------------------------------------
          card.addEventListener("mouseenter", (e) => {
            if (window.showUnitTooltip) {
              window.showUnitTooltip(unit, gameState.uiMetadata, e);
            }
          });

          card.addEventListener("mousemove", (e) => {
            if (window.moveUnitTooltip) {
              window.moveUnitTooltip(e);
            }
          });

          card.addEventListener("mouseleave", () => {
            if (window.hideUnitTooltip) {
              window.hideUnitTooltip();
            }
          });

          // ---------------------------------------------
          // Assemble card
          // ---------------------------------------------
          card.appendChild(counter);
          card.appendChild(hpBar);   // ✅ corazones aquí
          card.appendChild(name);
          scroll.appendChild(card);
        });

        sideBlock.appendChild(scroll);
        container.appendChild(sideBlock);
      });
    }
  };
};