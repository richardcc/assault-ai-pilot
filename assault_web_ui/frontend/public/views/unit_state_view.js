// =================================================
// UNIT STATE VIEW (Columns by side, horizontal scroll)
// Alive units show COUNTER
// Dead units show SIDE DEAD MARKER
// =================================================

window.renderUnitStateView = function renderUnitStateView(gameState) {

  return {
    render(container) {

      const unitsState = gameState.units;
      const unitDefs  = gameState.uiMetadata?.units;
      const sideMeta  = gameState.uiMetadata?.sides;

      if (!unitsState || Object.keys(unitsState).length === 0) {
        container.innerHTML = "<em>No units</em>";
        return;
      }

      container.innerHTML = "";

      // -------------------------------------------------
      // Group units by side
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

        const sideBlock = document.createElement("div");
        sideBlock.className = "unit-state-side";

        const header = document.createElement("div");
        header.className = "unit-state-side-header";
        header.textContent = side;
        sideBlock.appendChild(header);

        const scroll = document.createElement("div");
        scroll.className = "unit-state-scroll";

        units.forEach(unit => {

          const card = document.createElement("div");
          card.className = "unit-card";
          card.dataset.unitId = unit.unit_id;

          // -------------------------------------------------
          // 🔥 TOOLTIP (HOVER)
          // -------------------------------------------------
          card.addEventListener("mouseenter", (evt) => {
            if (window.showUnitTooltip) {
              window.showUnitTooltip(unit, gameState.uiMetadata, evt);
            }
          });

          card.addEventListener("mousemove", (evt) => {
            if (window.moveUnitTooltip) {
              window.moveUnitTooltip(evt);
            }
          });

          card.addEventListener("mouseleave", () => {
            if (window.hideUnitTooltip) {
              window.hideUnitTooltip();
            }
          })
          // ---------------------------------------------
          // IMAGE
          // ---------------------------------------------
          const counter = document.createElement("div");
          counter.className = "unit-card-counter";

          let imgSrc = null;

          if (unit.alive === false) {
            imgSrc = sideMeta?.[unit.side]?.dead_marker;
          } else {
            const def = unitDefs?.[unit.unit_key];
            if (def?.full) {
              imgSrc = "/public/art/counters/" + def.full;
            }
          }

          if (imgSrc) {
            const img = document.createElement("img");
            img.src = imgSrc;
            img.alt = unit.unit_id;
            counter.appendChild(img);
          }

          // ---------------------------------------------
          // ❤️ HP
          // ---------------------------------------------
          const hpBar = document.createElement("div");
          hpBar.className = "unit-card-hp";

          const hp = Number(unit.hp) || 0;
          for (let i = 0; i < hp; i++) {
            const heart = document.createElement("span");
            heart.className = "unit-heart";
            heart.textContent = "❤️";
            hpBar.appendChild(heart);
          }

          // ---------------------------------------------
          // 📍 POSITION
          // ---------------------------------------------
          const pos = document.createElement("div");
          pos.className = "unit-card-pos";

          const q = unit.position?.q;
          const r = unit.position?.r;

          pos.textContent = (q !== undefined && r !== undefined)
            ? `(${q},${r})`
            : "-";

          // ---------------------------------------------
          // Label
          // ---------------------------------------------
          const name = document.createElement("div");
          name.className = "unit-card-name";
          name.textContent = unit.unit_id;

          // ---------------------------------------------
          // Assemble card
          // ---------------------------------------------
          card.appendChild(counter);
          card.appendChild(hpBar);
          card.appendChild(pos);   // ✅ CLAVE
          card.appendChild(name);

          scroll.appendChild(card);
        });

        sideBlock.appendChild(scroll);
        container.appendChild(sideBlock);
      });
    }
  };
};