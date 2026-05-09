// -------------------------------------------------
// PixiJS bootstrap – Phase 2
// FASE FINAL (CONNECTED EVENT LOG + COMBAT PANEL)
// -------------------------------------------------

// ---------------- ROOT ----------------
const root = document.getElementById("pixi-root");

// ---------------- PIXI APP ----------------
const app = new PIXI.Application({
  resizeTo: root,
  backgroundColor: 0x1e1e1e,
  antialias: true
});
root.appendChild(app.view);

// ---------------- MAP ----------------
renderGrid(app, SCENARIO);

// ---------------- UNIT IMAGES ----------------
const UNIT_IMAGE_MAP = {
  GE_RIFLES_43: "/public/assets/counters/GE Rifles 43.png",
  US_RIFLES_43: "/public/assets/counters/US Rifles 43.png",
  GE_FJ_RIFLES_43: "/public/assets/counters/GE FJ Rifles 43.png",
  US_RANGERS_43: "/public/assets/counters/US Rangers 43.png"
};

// ---------------- REPLAY STATE ----------------
let REPLAY = null;
let replayUnits = {};
let CURRENT_TURN = 0;
let CURRENT_STEP = -1;

// ---------------- COMBAT PANEL ----------------
const combatPanelEl = document.querySelector(".combat .box");

function clearCombatPanel() {
  combatPanelEl.innerHTML = "COMBAT PANEL";
}

function renderCombatPanel(event) {
  clearCombatPanel();

  if (!event || event.type !== "ACTION_EFFECT") return;

  const payload = event.payload;
  if (!payload || !payload.action) return;

  if (payload.action === "RangedCombat") {
    combatPanelEl.innerHTML = renderRangedCombat(
      payload,
      unitId => unitId
    );
  }
}

// ---------------- HEADER ----------------
function updateHeaderTurnStep() {
  const el = document.getElementById("header-turn-step");
  if (!el || !REPLAY) return;

  const totalTurns = REPLAY.turns.length;
  const currentTurn = CURRENT_TURN + 1;

  const totalSteps =
    REPLAY.turns[CURRENT_TURN]?.events.length || 0;

  const currentStep = Math.max(CURRENT_STEP + 1, 0);

  el.textContent =
    `TURN ${currentTurn} / ${totalTurns} · STEP ${currentStep} / ${totalSteps}`;
}

// ---------------- LOAD REPLAY ----------------
async function loadReplay(url) {
  const res = await fetch(url);
  REPLAY = await res.json();
  console.log("✅ Replay loaded");
}

// ---------------- BUILD UNITS ----------------
function buildUnitsFromReplay() {
  replayUnits = {};

  REPLAY.initial_state.units.forEach(u => {
    replayUnits[u.id] = {
      id: u.id,
      side: u.side,
      q: u.q,
      r: u.r,
      hp: u.hp,
      strength: u.hp,
      steps: u.hp,
      name: u.type.replaceAll("_", " "),
      status: ["READY"],
      type: u.type,
      image: UNIT_IMAGE_MAP[u.type] || null
    };
  });
}

// ---------------- RENDER ----------------
function renderReplayUnits() {
  renderUnitsOnMap(app, {
    ...SCENARIO,
    units: Object.values(replayUnits)
  });
}

function updateSidebarFromReplay() {
  renderUnitSidebar(Object.values(replayUnits));
}

// ---------------- APPLY EVENT (STATE ONLY) ----------------
function applyReplayEvent(event) {

  if (event.type === "UNIT_MOVED") {
    const u = replayUnits[event.payload.unit_id];
    if (!u) return;
    u.q = event.payload.to.q;
    u.r = event.payload.to.r;
  }

  if (event.type === "ACTION_EFFECT") {
    const u = replayUnits[event.payload.defender];
    if (!u) return;

    u.hp = event.payload.defender_hp_after;
    u.steps = event.payload.defender_hp_after;
    u.strength = event.payload.defender_hp_after;

    if (event.payload.defender_killed) {
      u.status = ["KIA"];
      u.q = null;
      u.r = null;
    }
  }
}

// ---------------- REBUILD ----------------
function rebuildState(turnIndex, stepIndex) {
  buildUnitsFromReplay();
  clearEventLog();
  clearCombatPanel();

  for (let t = 0; t < turnIndex; t++) {
    REPLAY.turns[t].events.forEach(e => {
      applyReplayEvent(e);
      const text = formatReplayEvent(e);
      if (text) appendEventLog(text);
    });
  }

  if (stepIndex >= 0) {
    const events = REPLAY.turns[turnIndex].events;
    for (let s = 0; s <= stepIndex; s++) {
      applyReplayEvent(events[s]);
      const text = formatReplayEvent(events[s]);
      if (text) appendEventLog(text);
    }
  }

  renderReplayUnits();
  updateSidebarFromReplay();
  updateHeaderTurnStep();
}

// ---------------- STEP NAVIGATION ----------------
function nextStep() {
  const turn = REPLAY.turns[CURRENT_TURN];
  if (!turn) return;

  let event = null;

  if (CURRENT_STEP + 1 < turn.events.length) {
    CURRENT_STEP++;
    event = turn.events[CURRENT_STEP];
  } else if (CURRENT_TURN + 1 < REPLAY.turns.length) {
    CURRENT_TURN++;
    CURRENT_STEP = 0;
    event = REPLAY.turns[CURRENT_TURN].events[0];
  }

  if (!event) return;

  applyReplayEvent(event);
  const text = formatReplayEvent(event);
  if (text) appendEventLog(text);

  renderReplayUnits();
  updateSidebarFromReplay();
  updateHeaderTurnStep();
  renderCombatPanel(event);
}

// ---------------- TURN NAVIGATION ----------------
function nextTurn() {
  if (CURRENT_TURN + 1 >= REPLAY.turns.length) return;

  CURRENT_TURN++;
  CURRENT_STEP = -1;
  clearCombatPanel();

  const turn = REPLAY.turns[CURRENT_TURN];

  turn.events.forEach(e => {
    applyReplayEvent(e);
    const text = formatReplayEvent(e);
    if (text) appendEventLog(text);
  });

  renderReplayUnits();
  updateSidebarFromReplay();
  updateHeaderTurnStep();
}

function prevStep() {
  if (CURRENT_STEP > 0) {
    CURRENT_STEP--;
  } else if (CURRENT_TURN > 0) {
    CURRENT_TURN--;
    CURRENT_STEP = REPLAY.turns[CURRENT_TURN].events.length - 1;
  }
  rebuildState(CURRENT_TURN, CURRENT_STEP);
}

function prevTurn() {
  if (CURRENT_TURN <= 0) return;
  CURRENT_TURN--;
  CURRENT_STEP = -1;
  rebuildState(CURRENT_TURN, CURRENT_STEP);
}

// ---------------- BOOTSTRAP ----------------
async function bootstrapReplay() {
  await loadReplay(
    "/public/replays/phase01_seq001_initial_contact__US_RL_vs_GE_HEURISTIC.json"
  );

  rebuildState(0, -1);

  document.getElementById("btn-next-turn").onclick = nextTurn;
  document.getElementById("btn-prev-turn").onclick = prevTurn;
  document.getElementById("btn-next-step").onclick = nextStep;
  document.getElementById("btn-prev-step").onclick = prevStep;
}

bootstrapReplay();