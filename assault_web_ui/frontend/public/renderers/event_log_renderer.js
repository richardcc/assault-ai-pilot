// -------------------------------------------------
// Event Log Renderer
// -------------------------------------------------
// Responsible ONLY for rendering the event log UI
// - No game logic
// - No state mutation
// - Supports rebuild & incremental update
// -------------------------------------------------

function clearEventLog() {
  const log = document.getElementById("event-log");
  if (!log) return;
  log.innerHTML = "";
}

function appendEventLog(text) {
  const log = document.getElementById("event-log");
  if (!log) return;

  const entry = document.createElement("div");
  entry.className = "event-log-entry";
  entry.textContent = text;

  log.appendChild(entry);
  log.scrollTop = log.scrollHeight;
}

// -------------------------------------------------
// Render FULL log for current replay cursor
// (Used on load, turn jump, prev, rebuild)
// -------------------------------------------------
function renderEventLogFromState(gameState) {
  clearEventLog();

  const replay = gameState.replay;
  const cursor = gameState.replayCursor;
  if (!replay) return;

  for (let t = 0; t <= cursor.turnIndex; t++) {
    const turn = replay.turns[t];
    if (!turn) continue;

    for (let e = 0; e < turn.events.length; e++) {
      if (t === cursor.turnIndex && e >= cursor.eventIndex) break;

      const text = formatReplayEvent(turn.events[e]);
      if (text) appendEventLog(text);
    }
  }
}

// -------------------------------------------------
// Append ONLY last event (incremental step)
// -------------------------------------------------
function appendLastReplayEvent(gameState) {
  const replay = gameState.replay;
  const cursor = gameState.replayCursor;
  if (!replay) return;

  const turn = replay.turns[cursor.turnIndex];
  if (!turn) return;

  const event = turn.events[cursor.eventIndex - 1];
  if (!event) return;

  const text = formatReplayEvent(event);
  if (text) appendEventLog(text);
}

// -------------------------------------------------
// Format replay events into readable text
// -------------------------------------------------
function formatReplayEvent(event) {
  if (!event) return null;

  if (event.type === "ACTION") {
    return `ACTION · ${event.payload.active_unit} · ${event.payload.action}`;
  }

  if (event.type === "UNIT_MOVED") {
    const { unit_id, from, to } = event.payload;
    return `MOVE · ${unit_id} · ${from.q},${from.r} → ${to.q},${to.r}`;
  }

  if (event.type === "ACTION_EFFECT") {
    const p = event.payload;

    if (p.defender_killed) {
      return `KIA · ${p.defender} killed by ${p.attacker}`;
    }

    return `HIT · ${p.attacker} → ${p.defender} (${p.defender_hp_before} → ${p.defender_hp_after})`;
  }

  return null;
}

// -------------------------------------------------
// ✅ PUBLIC API
// -------------------------------------------------
window.clearEventLog = clearEventLog;
window.appendEventLog = appendEventLog;
window.renderEventLogFromState = renderEventLogFromState;
window.appendLastReplayEvent = appendLastReplayEvent;
window.formatReplayEvent = formatReplayEvent;
