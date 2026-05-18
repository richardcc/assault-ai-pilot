// mock_state.js
// ====================================
// Logical scenario + FINAL render-ready map
// ====================================

window.SCENARIO = {
  id: "mettete_i_piedi_terra_1_min",
  maxTurns: 12,

  // --------------------------------------------------
  // Authoritative grid definition (binding)
  // --------------------------------------------------
  grid: {
    type: "hex",
    orientation: "pointy",
    hexRadius: 52,
    layout: "row-offset"
  },

  // --------------------------------------------------
  // Terrain pieces (logical definition ONLY)
  // --------------------------------------------------
  pieces: {

    // ---------- S3 (UPPER MAP) ----------
    S3: {
      description: "Upper map section 9x8",
      render: {
        image: "/public/assets/maps/Map_S3.png",
        anchorHex: { q: 0, r: 0 } // A1
      },
      hexes: [
        [{q:0,r:0,terrain:"clear"},{q:1,r:0,terrain:"clear"},{q:2,r:0,terrain:"clear"},{q:3,r:0,terrain:"clear"},{q:4,r:0,terrain:"clear"},{q:5,r:0,terrain:"clear"},{q:6,r:0,terrain:"clear"},{q:7,r:0,terrain:"clear"},{q:8,r:0,terrain:"clear"}],
        [{q:0,r:1,terrain:"clear"},{q:1,r:1,terrain:"clear"},{q:2,r:1,terrain:"clear"},{q:3,r:1,terrain:"clear"},{q:4,r:1,terrain:"clear"},{q:5,r:1,terrain:"clear"},{q:6,r:1,terrain:"clear"},{q:7,r:1,terrain:"clear"},{q:8,r:1,terrain:"clear"}],
        [{q:0,r:2,terrain:"clear"},{q:1,r:2,terrain:"clear"},{q:2,r:2,terrain:"clear"},{q:3,r:2,terrain:"clear"},{q:4,r:2,terrain:"clear"},{q:5,r:2,terrain:"clear"},{q:6,r:2,terrain:"clear"},{q:7,r:2,terrain:"clear"},{q:8,r:2,terrain:"clear"}],
        [{q:0,r:3,terrain:"clear"},{q:1,r:3,terrain:"clear"},{q:2,r:3,terrain:"clear"},{q:3,r:3,terrain:"clear"},{q:4,r:3,terrain:"clear"},{q:5,r:3,terrain:"clear"},{q:6,r:3,terrain:"clear"},{q:7,r:3,terrain:"clear"},{q:8,r:3,terrain:"clear"}],
        [{q:0,r:4,terrain:"clear"},{q:1,r:4,terrain:"clear"},{q:2,r:4,terrain:"clear"},{q:3,r:4,terrain:"clear"},{q:4,r:4,terrain:"clear"},{q:5,r:4,terrain:"clear"},{q:6,r:4,terrain:"clear"},{q:7,r:4,terrain:"clear"},{q:8,r:4,terrain:"clear"}],
        [{q:0,r:5,terrain:"clear"},{q:1,r:5,terrain:"clear"},{q:2,r:5,terrain:"clear"},{q:3,r:5,terrain:"clear"},{q:4,r:5,terrain:"clear"},{q:5,r:5,terrain:"clear"},{q:6,r:5,terrain:"clear"},{q:7,r:5,terrain:"clear"},{q:8,r:5,terrain:"clear"}],
        [{q:0,r:6,terrain:"clear"},{q:1,r:6,terrain:"clear"},{q:2,r:6,terrain:"clear"},{q:3,r:6,terrain:"clear"},{q:4,r:6,terrain:"clear"},{q:5,r:6,terrain:"clear"},{q:6,r:6,terrain:"clear"},{q:7,r:6,terrain:"clear"},{q:8,r:6,terrain:"clear"}],
        [{q:0,r:7,terrain:"clear"},{q:1,r:7,terrain:"clear"},{q:2,r:7,terrain:"clear"},{q:3,r:7,terrain:"clear"},{q:4,r:7,terrain:"clear"},{q:5,r:7,terrain:"clear"},{q:6,r:7,terrain:"clear"},{q:7,r:7,terrain:"clear"},{q:8,r:7,terrain:"clear"}]
      ]
    },

    // ---------- S2 (LOWER MAP) ----------
    S2: {
      description: "Lower map section 9x8",
      render: {
        image: "/public/assets/maps/Map_S2.png",
        anchorHex: { q: 0, r: 8 } // A9
      },
      hexes: [
        [{q:0,r:0,terrain:"clear"},{q:1,r:0,terrain:"clear"},{q:2,r:0,terrain:"clear"},{q:3,r:0,terrain:"clear"},{q:4,r:0,terrain:"clear"},{q:5,r:0,terrain:"clear"},{q:6,r:0,terrain:"clear"},{q:7,r:0,terrain:"clear"},{q:8,r:0,terrain:"clear"}],
        [{q:0,r:1,terrain:"clear"},{q:1,r:1,terrain:"clear"},{q:2,r:1,terrain:"clear"},{q:3,r:1,terrain:"clear"},{q:4,r:1,terrain:"clear"},{q:5,r:1,terrain:"clear"},{q:6,r:1,terrain:"clear"},{q:7,r:1,terrain:"clear"},{q:8,r:1,terrain:"clear"}],
        [{q:0,r:2,terrain:"clear"},{q:1,r:2,terrain:"clear"},{q:2,r:2,terrain:"clear"},{q:3,r:2,terrain:"clear"},{q:4,r:2,terrain:"clear"},{q:5,r:2,terrain:"clear"},{q:6,r:2,terrain:"clear"},{q:7,r:2,terrain:"clear"},{q:8,r:2,terrain:"clear"}],
        [{q:0,r:3,terrain:"clear"},{q:1,r:3,terrain:"clear"},{q:2,r:3,terrain:"clear"},{q:3,r:3,terrain:"clear"},{q:4,r:3,terrain:"clear"},{q:5,r:3,terrain:"clear"},{q:6,r:3,terrain:"clear"},{q:7,r:3,terrain:"clear"},{q:8,r:3,terrain:"clear"}],
        [{q:0,r:4,terrain:"clear"},{q:1,r:4,terrain:"clear"},{q:2,r:4,terrain:"clear"},{q:3,r:4,terrain:"clear"},{q:4,r:4,terrain:"clear"},{q:5,r:4,terrain:"clear"},{q:6,r:4,terrain:"clear"},{q:7,r:4,terrain:"clear"},{q:8,r:4,terrain:"clear"}],
        [{q:0,r:5,terrain:"water"},{q:1,r:5,terrain:"water"},{q:2,r:5,terrain:"water"},{q:3,r:5,terrain:"water"},{q:4,r:5,terrain:"water"},{q:5,r:5,terrain:"water"},{q:6,r:5,terrain:"water"},{q:7,r:5,terrain:"water"},{q:8,r:5,terrain:"water"}],
        [{q:0,r:6,terrain:"water"},{q:1,r:6,terrain:"water"},{q:2,r:6,terrain:"water"},{q:3,r:6,terrain:"water"},{q:4,r:6,terrain:"water"},{q:5,r:6,terrain:"water"},{q:6,r:6,terrain:"water"},{q:7,r:6,terrain:"water"},{q:8,r:6,terrain:"water"}],
        [{q:0,r:7,terrain:"water"},{q:1,r:7,terrain:"water"},{q:2,r:7,terrain:"water"},{q:3,r:7,terrain:"water"},{q:4,r:7,terrain:"water"},{q:5,r:7,terrain:"water"},{q:6,r:7,terrain:"water"},{q:7,r:7,terrain:"water"},{q:8,r:7,terrain:"water"}]
      ]
    }
  },

  // --------------------------------------------------
  // ✅ UNITS (para el SIDEBAR)
  // --------------------------------------------------
  units: [
    {
      id: "GE_FJ_43",
      side: "GE",
      name: "FJ Rifles 43",
      image: "/public/assets/counters/GE FJ Rifles 43.png",
      strength: 5,
      steps: 3,
      status: ["READY"],
      q: 3,
      r: 5

    },
    {
      id: "US_RIF_43",
      side: "US",
      name: "US Rifles 43",
      image: "/public/assets/counters/US Rifles 43.png",
      strength: 4,
      steps: 2,
      status: ["MOVED"],
      q: 4,
      r: 6
    }
  ]
};

// --------------------------------------------------
// Build FINAL MAP (renderer authority)
// --------------------------------------------------
(function buildFinalMap() {
  const hexes = [];
  const s3 = window.SCENARIO.pieces.S3.hexes;
  const s2 = window.SCENARIO.pieces.S2.hexes;
  const offset = s3.length;

  s3.forEach(row =>
    row.forEach(h =>
      hexes.push({ q: h.q, r: h.r, terrain: h.terrain })
    )
  );

  s2.forEach(row =>
    row.forEach(h =>
      hexes.push({ q: h.q, r: h.r + offset, terrain: h.terrain })
    )
  );

  window.SCENARIO.map = {
    width: 9,
    height: offset * 2,
    hexes
  };
})();