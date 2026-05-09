// -------------------------------------------------
// PixiJS bootstrap – Phase 2
// FASE 3
// - Render static map from mock
// - Load replay
// - Build replay state
// - Map unit type -> image (UI only)
// - Render units FROM replay
// - Adapt data for sidebar contract
// -------------------------------------------------

// -------------------------------------------------
// 1) Root container
// -------------------------------------------------
const root = document.getElementById("pixi-root");

// -------------------------------------------------
// 2) Pixi application
// -------------------------------------------------
const app = new PIXI.Application({
  resizeTo: root,
  backgroundColor: 0x1e1e1e,
  antialias: true
});

root.appendChild(app.view);

// -------------------------------------------------
// 3) Render static scenario (mock authority for MAP)
// -------------------------------------------------
renderGrid(app, SCENARIO);

// -------------------------------------------------
// 4) UI-only unit image catalog
// -------------------------------------------------
const UNIT_IMAGE_MAP = {
  "GE_RIFLES_43": "/public/assets/counters/GE Rifles 43.png",
  "US_RIFLES_43": "/public/assets/counters/US Rifles 43.png",
  "GE_FJ_RIFLES_43": "/public/assets/counters/GE FJ Rifles 43.png",
  "US_RANGERS_43": "/public/assets/counters/US Rangers 43.png"
};

// -------------------------------------------------
// 5) Replay state
// -------------------------------------------------
let REPLAY = null;
let replayUnits = {};

// -------------------------------------------------
// 6) Load replay JSON
// -------------------------------------------------
async function loadReplay(url) {
  const res = await fetch(url);
  REPLAY = await res.json();
  console.log("✅ Replay loaded:", REPLAY);
}

// -------------------------------------------------
// 7) Build unit state from replay.initial_state
//    (ADAPTED TO SIDEBAR CONTRACT)
// -------------------------------------------------
function buildUnitsFromReplay() {
  replayUnits = {};

  REPLAY.initial_state.units.forEach(u => {
    replayUnits[u.id] = {
      // Identity
      id: u.id,
      side: u.side,

      // Map position
      q: u.q,
      r: u.r,

      // Combat state
      hp: u.hp,
      strength: u.hp,
      steps: u.hp,

      // ✅ Sidebar-required fields
      name: u.type.replaceAll("_", " "),
      status: ["READY"],

      // Rendering
      type: u.type,
      image: UNIT_IMAGE_MAP[u.type] || null
    };
  });

  console.log("✅ Replay units built:", replayUnits);
}

// -------------------------------------------------
// 8) Render units FROM replay (not mock)
// -------------------------------------------------
function renderReplayUnits() {
  const scenarioForReplay = {
    ...SCENARIO,
    units: Object.values(replayUnits)
  };

  renderUnitsOnMap(app, scenarioForReplay);
}

// -------------------------------------------------
// 9) Update sidebar from replay
// -------------------------------------------------
function updateSidebarFromReplay() {
  if (typeof renderUnitSidebar === "function") {
    renderUnitSidebar(Object.values(replayUnits));
  }
}

// -------------------------------------------------
// 10) Bootstrap (FASE 3)
// -------------------------------------------------
async function bootstrapReplay() {
  await loadReplay(
    "/public/replays/phase01_seq001_initial_contact__US_RL_vs_GE_HEURISTIC.json"
  );

  buildUnitsFromReplay();
  renderReplayUnits();
  updateSidebarFromReplay();
}

bootstrapReplay();