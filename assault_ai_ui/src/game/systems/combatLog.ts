import { unitImages } from "../config/unitImages";

/**
 * combatLog.ts
 *
 * Shared formatting + de-duplicated logging for combat ACTION_EFFECT events.
 *
 * Combat events can reach the frontend through several paths (human step,
 * AI step runner, ai-turn endpoint, websocket). React batching can drop the
 * intermediate state that carries `last_events`, so we log directly from the
 * backend responses instead of relying on a render effect, and dedupe by the
 * stable event id assigned on the backend.
 */

const loggedIds = new Set<string>();

const COLOR_SQ: Record<string, string> = {
  RED: "🟥",
  YELLOW: "🟨",
  GREEN: "🟩",
  BLUE: "🟦",
};

const FACE_SYM: Record<string, string> = {
  CRITICAL: "💥",
  DAMAGE: "🩸",
  SUPPRESS: "💨",
};

function faceStr(faces: any): string {
  const arr = Array.isArray(faces) ? faces : faces ? [faces] : [];
  if (!arr.length) return "▫️"; // blank face
  return arr
    .map((f: any) => FACE_SYM[String(f || "").toUpperCase()] || "")
    .join("");
}

function diceStr(dice: any[] = []): string {
  return (
    (dice || [])
      .map((d) => {
        const color = COLOR_SQ[String(d?.color || "").toUpperCase()] || "⬜";
        return color + faceStr(d?.faces);
      })
      .join(" ") || "—"
  );
}

function labelFor(id: string | null | undefined, units: any[]): string {
  if (!id) return "Unknown";
  const unitId = String(id);
  const u = units?.find((x: any) => String(x.id) === unitId);
  if (!u) return unitId;
  const name =
    unitImages[u.unit_key as keyof typeof unitImages]?.label || u.unit_key;
  return name ? `${unitId} (${name})` : unitId;
}

export function formatCombatEvent(
  ev: any,
  units: any[] = []
): { type: string; text: string } | null {
  const p = ev?.payload || {};
  if (ev?.type === "REACTION_FIRE") {
    const reactor = labelFor(p.reactor_id, units);
    const target = labelFor(p.target_id, units);
    return {
      type: "combat",
      text: `⚡ Reaction Fire: ${reactor} -> ${target}`,
    };
  }
  const atk = labelFor(p.attacker, units);
  const def = labelFor(p.defender, units);

  if (p.action === "CloseCombat") {
    let atkDmg = 0;
    let defDmg = 0;
    for (const r of p.rounds || []) {
      if (typeof r.attacker_hp_before === "number" && typeof r.attacker_hp_after === "number") {
        atkDmg += Math.max(0, r.attacker_hp_before - r.attacker_hp_after);
      }
      if (typeof r.defender_hp_before === "number" && typeof r.defender_hp_after === "number") {
        defDmg += Math.max(0, r.defender_hp_before - r.defender_hp_after);
      }
    }
    let text = `⚔️ Close combat ${atk} ↔ ${def} — ${atk}: -${atkDmg} HP / ${def}: -${defDmg} HP${p.outcome ? ` (${p.outcome})` : ""}`;
    const r0 = (p.rounds || [])[0];
    if (r0) {
      text += ` | R1 ${atk} ATK ${diceStr(r0.attacker_attack_dice)} DEF ${diceStr(r0.attacker_defense_dice)} · ${def} ATK ${diceStr(r0.defender_attack_dice)} DEF ${diceStr(r0.defender_defense_dice)}`;
    }
    return { type: "combat", text };
  }

  const before = p.defender_hp_before;
  const after = p.defender_hp_after;
  const dmg =
    typeof before === "number" && typeof after === "number"
      ? Math.max(0, before - after)
      : null;
  if (dmg == null) return null;

  const crits = (p.attacker_effects?.criticals || p.criticals || []).length;
  const suppress = p.attacker_effects?.suppress || 0;
  const killed = p.defender_killed || p.defender_destroyed || p.killed;

  let text = `🎯 ${atk} → ${def}: ${dmg > 0 ? `-${dmg} HP` : "no damage"}`;
  if (crits > 0) text += ` · 💥 ${crits} crit`;
  if (suppress > 0) text += ` · 😰 suppressed`;
  if (killed) text += ` · ☠️ ${def} destroyed`;
  text += ` | ATK ${diceStr(p.attacker_attack_dice)} · DEF ${diceStr(p.defender_defense_dice)}`;
  return { type: "combat", text };
}

/**
 * Log all combat events from a `last_events` array, skipping any already logged.
 */
export function logCombatEvents(
  events: any[] | undefined | null,
  units: any[] = []
): void {
  if (!events?.length) return;

  for (const ev of events) {
    if (ev?.type !== "ACTION_EFFECT" && ev?.type !== "REACTION_FIRE") continue;

    const id =
      ev.id != null ? `id:${ev.id}` : `sig:${JSON.stringify(ev.payload || {})}`;
    if (loggedIds.has(id)) continue;
    loggedIds.add(id);

    const formatted = formatCombatEvent(ev, units);
    if (formatted) {
      (window as any).logSystemEvent?.(formatted.type, formatted.text);
    }
  }

  if (loggedIds.size > 1000) {
    loggedIds.clear();
  }
}
