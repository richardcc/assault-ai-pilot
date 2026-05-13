// =================================================
// EVENT LOG VIEW
// =================================================
// Responsible ONLY for rendering the event log UI
// - No game logic
// - No state mutation
// - Supports rebuild & incremental update
// =================================================

// -------------------------------------------------
// Clear entire log
// -------------------------------------------------
function clearEventLog() {
  const log = document.getElementById("event-log");
  if (!log) return;
  log.innerHTML = "";
}

// -------------------------------------------------
// Append single log entry
// -------------------------------------------------
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
// Rebuild FULL log from current replay cursor
// Used on:
// - Initial load
// - Next Turn / Prev Turn
// - Prev Step
// -------------------------------------------------
function rebuildEventLogFromState(gameState) {
  clearEventLog();

  const replay = gameState.replay;
  const cursor = gameState.replayCursor;
  if (!replay || !cursor) return;

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
// Append LAST event only (incremental step)
// Used on:
// - Next Step
// -------------------------------------------------
function appendLastReplayEvent(gameState) {
  const replay = gameState.replay;
  const cursor = gameState.replayCursor;
  if (!replay || !cursor) return;

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

  switch (event.type) {

    case "ACTION": {
      const p = event.payload;
      return `ACTION · ${p.active_unit} · ${p.action}`;
    }

    case "UNIT_MOVED": {
      const { unit_id, from, to } = event.payload;
      return `MOVE · ${unit_id} · ${from.q},${from.r} → ${to.q},${to.r}`;
    }

    case "ACTION_EFFECT": {
      const p = event.payload;

      if (p.defender_killed) {
        return `KIA · ${p.defender} killed by ${p.attacker}`;
      }

      return `HIT · ${p.attacker} → ${p.defender} (${p.defender_hp_before} → ${p.defender_hp_after})`;
    }

    default:
      return null;
  }
}

// -------------------------------------------------
// ✅ PUBLIC VIEW API
// -------------------------------------------------
window.clearEventLog            = clearEventLog;
window.appendEventLog           = appendEventLog;
window.rebuildEventLogFromState = rebuildEventLogFromState;
window.appendLastReplayEvent    = appendLastReplayEvent;
window.formatReplayEvent        = formatReplayEvent;
