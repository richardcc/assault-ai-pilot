// =================================================
// EVENT LOG VIEW (PRO VERSION)
// Clean + grouped + readable + game-like
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
// Append entry
// -------------------------------------------------
function appendEventLog(text) {
  const log = document.getElementById("event-log");
  if (!log) return;

  const entry = document.createElement("div");
  entry.className = "event-log-entry";

  entry.innerText = text;

  log.appendChild(entry);
  log.scrollTop = log.scrollHeight;
}


// -------------------------------------------------
// Get readable unit label
// -------------------------------------------------
function getUnitLabel(gameState, id) {
  const unit = gameState.units[id];
  const meta = gameState.uiMetadata?.units;

  if (!unit || !meta) return id;

  const def = meta[unit.unit_key];

  return def?.label
    ? `${def.label} (${id})`
    : id;
}


// -------------------------------------------------
// Format event (PRO)
// -------------------------------------------------
function formatReplayEvent(event, gameState) {
  if (!event) return null;

  switch (event.type) {

    // ---------------------------------------------
    // MOVE
    // ---------------------------------------------
    case "UNIT_MOVED": {
      const { unit_id, from, to } = event.payload;

      return `🚶 ${getUnitLabel(gameState, unit_id)}
Move: ${from.q},${from.r} → ${to.q},${to.r}`;
    }

    // ---------------------------------------------
    // COMBAT
    // ---------------------------------------------
    case "ACTION_EFFECT": {
      const p = event.payload;

      // 💀 killed
      if (p.defender_killed) {
        return `💀 ${getUnitLabel(gameState, p.defender)}
killed by ${getUnitLabel(gameState, p.attacker)}`;
      }

      // 🟡 suppressed
      if (p.resolution?.remaining_suppress > 0) {
        return `🟡 ${getUnitLabel(gameState, p.defender)}
suppressed by ${getUnitLabel(gameState, p.attacker)}`;
      }

      // 🔥 normal hit
      return `💥 ${getUnitLabel(gameState, p.attacker)} → ${getUnitLabel(gameState, p.defender)}
HP ${p.defender_hp_before} → ${p.defender_hp_after}`;
    }

    // ---------------------------------------------
    // ACTION (filter move)
    // ---------------------------------------------
    case "ACTION":
      if (event.payload?.action === "MoveAction") return null;
      return `⚡ ${event.payload.active_unit} · ${event.payload.action}`;

    default:
      return null;
  }
}


// -------------------------------------------------
// Rebuild FULL log with TURN separators
// -------------------------------------------------
function rebuildEventLogFromState(gameState) {
  clearEventLog();

  const replay = gameState.replay;
  const cursor = gameState.replayCursor;

  if (!replay || !cursor) return;

  for (let t = 0; t <= cursor.turnIndex; t++) {

    appendEventLog(`──── TURN ${t + 1} ────`);

    const turn = replay.turns[t];
    if (!turn) continue;

    for (let e = 0; e < turn.events.length; e++) {

      if (t === cursor.turnIndex && e >= cursor.eventIndex) break;

      const text = formatReplayEvent(turn.events[e], gameState);

      if (text) appendEventLog(text);
    }
  }
}


// -------------------------------------------------
// Append incremental
// -------------------------------------------------
function appendLastReplayEvent(gameState) {
  const replay = gameState.replay;
  const cursor = gameState.replayCursor;

  if (!replay || !cursor) return;

  const turn = replay.turns[cursor.turnIndex];
  if (!turn) return;

  const event = turn.events[cursor.eventIndex - 1];
  if (!event) return;

  const text = formatReplayEvent(event, gameState);

  if (text) appendEventLog(text);
}


// -------------------------------------------------
// EXPORT
// -------------------------------------------------
window.clearEventLog            = clearEventLog;
window.appendEventLog           = appendEventLog;
window.rebuildEventLogFromState = rebuildEventLogFromState;
window.appendLastReplayEvent    = appendLastReplayEvent;
window.formatReplayEvent        = formatReplayEvent;
