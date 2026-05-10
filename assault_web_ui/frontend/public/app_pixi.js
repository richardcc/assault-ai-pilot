// -------------------------------------------------
// PixiJS bootstrap – Phase 2
// FINAL PHASE (CONNECTED EVENT LOG + COMBAT PANEL)
// -------------------------------------------------

// ---------------- ROOT ----------------
const root = document.getElementById("pixi-root");

// ---------------- PIXI APP ----------------
const app = new PIXI.Application({
  resizeTo: window,
  backgroundColor: 0x1e1e1e,
  antialias: true
});

root.appendChild(app.view);

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
  combatPanelEl.textContent = "COMBAT PANEL";
}

function renderCombatPanel(event) {
  clearCombatPanel();
  if (!event || event.type !== "ACTION_EFFECT") return;

  const payload = event.payload;
  if (!payload || !payload.action) return;

  if (payload.action === "RangedCombat") {
    combatPanelEl.innerHTML = renderRangedCombat(payload, unitId => unitId);
  }
}

// ---------------- LOAD REPLAY ----------------
async function loadReplay(url) {
  const res = await fetch(url);
  REPLAY = await res.json();
  console.log("Replay loaded");
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

// ---------------- APPLY EVENT ----------------
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
    u.steps = u.hp;
    u.strength = u.hp;

    if (event.payload.defender_killed) {
      u.status = ["KIA"];
      u.q = null;
      u.r = null;
    }
  }
}

// ---------------- HEADER CONTROLS BINDING ----------------
function bindHeaderControls() {
  const btnNextStep = document.getElementById("btn-next-step");
  const btnPrevStep = document.getElementById("btn-prev-step");
  const btnNextTurn = document.getElementById("btn-next-turn");
  const btnPrevTurn = document.getElementById("btn-prev-turn");

  if (btnNextStep) btnNextStep.onclick = nextStep;
  if (btnPrevStep) btnPrevStep.onclick = prevStep;
  if (btnNextTurn) btnNextTurn.onclick = nextTurn;
  if (btnPrevTurn) btnPrevTurn.onclick = prevTurn;
}

// ---------------- STATE REBUILD (DETERMINISTIC) ----------------
function rebuildState(targetTurn, targetStep) {
  // Reset to initial state
  buildUnitsFromReplay();

  CURRENT_TURN = 0;
  CURRENT_STEP = -1;

  clearCombatPanel();
  document.getElementById("event-log").innerHTML = "";

  // Replay state up to target position
  for (let t = 0; t <= targetTurn; t++) {
    const turn = REPLAY.turns[t];
    const events = turn.events;

    let lastIndex = events.length - 1;
    if (t === targetTurn) lastIndex = targetStep;

    for (let i = 0; i <= lastIndex; i++) {
      const event = events[i];
      applyReplayEvent(event);

      const text = formatReplayEvent(event);
      if (text) appendEventLog(text);
    }
  }

  CURRENT_TURN = targetTurn;
  CURRENT_STEP = targetStep;

  renderReplayUnits();
  updateSidebarFromReplay();
}

// ---------------- STEP NAVIGATION ----------------
function nextStep() {
  if (!REPLAY) return;
  if (CURRENT_TURN >= REPLAY.turns.length) return;

  let turn = REPLAY.turns[CURRENT_TURN];

  if (CURRENT_STEP + 1 >= turn.events.length) {
    if (CURRENT_TURN + 1 >= REPLAY.turns.length) return;
    CURRENT_TURN++;
    CURRENT_STEP = -1;
    return nextStep();
  }

  CURRENT_STEP++;
  turn = REPLAY.turns[CURRENT_TURN];
  const events = turn.events;

  while (CURRENT_STEP < events.length) {
    const event = events[CURRENT_STEP];

    applyReplayEvent(event);

    const text = formatReplayEvent(event);
    if (text) appendEventLog(text);

    const nextEvent = events[CURRENT_STEP + 1];
    if (!nextEvent || nextEvent.type === "ACTION") break;

    CURRENT_STEP++;
  }

  renderReplayUnits();
  updateSidebarFromReplay();

  renderHeader({
    scenario: SCENARIO,
    turn: CURRENT_TURN + 1,
    step: CURRENT_STEP + 1,
    totalTurns: REPLAY.turns.length,
    totalSteps: REPLAY.turns[CURRENT_TURN]?.events.length ?? 0
  });
  bindHeaderControls();

  renderCombatPanel(events[CURRENT_STEP]);
}

// ---------------- PREVIOUS STEP (ACTION-BASED) ----------------
function findPreviousAction(events, fromIndex) {
  for (let i = fromIndex - 1; i >= 0; i--) {
    if (events[i].type === "ACTION") return i;
  }
  return -1;
}

function prevStep() {
  if (!REPLAY) return;

  let turn = REPLAY.turns[CURRENT_TURN];
  let targetIndex = findPreviousAction(turn.events, CURRENT_STEP);

  if (targetIndex !== -1) {
    CURRENT_STEP = targetIndex;
  } else {
    if (CURRENT_TURN === 0) return;

    CURRENT_TURN--;
    turn = REPLAY.turns[CURRENT_TURN];

    for (let i = turn.events.length - 1; i >= 0; i--) {
      if (turn.events[i].type === "ACTION") {
        CURRENT_STEP = i;
        break;
      }
    }
  }

  rebuildState(CURRENT_TURN, CURRENT_STEP);

  renderHeader({
    scenario: SCENARIO,
    turn: CURRENT_TURN + 1,
    step: CURRENT_STEP + 1,
    totalTurns: REPLAY.turns.length,
    totalSteps: REPLAY.turns[CURRENT_TURN]?.events.length ?? 0
  });
  bindHeaderControls();
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

  renderHeader({
    scenario: SCENARIO,
    turn: CURRENT_TURN + 1,
    step: 0,
    totalTurns: REPLAY.turns.length,
    totalSteps: REPLAY.turns[CURRENT_TURN]?.events.length ?? 0
  });
  bindHeaderControls();
}

function prevTurn() {
  if (!REPLAY || CURRENT_TURN === 0) return;

  CURRENT_TURN--;
  CURRENT_STEP = -1;

  rebuildState(CURRENT_TURN, CURRENT_STEP);

  renderHeader({
    scenario: SCENARIO,
    turn: CURRENT_TURN + 1,
    step: 0,
    totalTurns: REPLAY.turns.length,
    totalSteps: REPLAY.turns[CURRENT_TURN]?.events.length ?? 0
  });
  bindHeaderControls();
}

// ---------------- BOOTSTRAP ----------------
async function bootstrapReplay() {
  await loadReplay(
    "/public/replays/phase01_seq001_initial_contact__US_RL_vs_GE_HEURISTIC.json"
  );

  renderGrid(app, SCENARIO);

  buildUnitsFromReplay();
  renderReplayUnits();
  updateSidebarFromReplay();

  renderHeader({
    scenario: SCENARIO,
    turn: 1,
    step: 0,
    totalTurns: REPLAY.turns.length,
    totalSteps: REPLAY.turns[0]?.events.length ?? 0
  });
  bindHeaderControls();
}

bootstrapReplay();