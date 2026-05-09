// -------------------------------------------------
// Event Log Renderer
// -------------------------------------------------
// Responsible ONLY for rendering the event log UI
// - No game logic
// - No state mutation
// - Scroll-safe
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

  // ✅ KEEP SCROLL AT BOTTOM
  log.scrollTop = log.scrollHeight;
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
// ✅ EXPOSE API GLOBALLY
// -------------------------------------------------
window.clearEventLog = clearEventLog;
window.appendEventLog = appendEventLog;
window.formatReplayEvent = formatReplayEvent;