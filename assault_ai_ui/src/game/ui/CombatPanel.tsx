import { useEffect, useState, useMemo } from "react";
import { unitImages } from "../config/unitImages";

type Unit = {
  id: string;
  unit_key: string;
  side: string;
  hp?: number;
  max_hp?: number;
  q: number;
  r: number;
};

type Payload = {
  action?: string;
  is_close_combat?: boolean;
  round_number?: number;
  attacker?: string;
  defender?: string;
  attacker_attack_dice?: any[];
  attack_dice?: any[];
  defender_defense_dice?: any[];
  defense_dice?: any[];
  distance?: number;
  attack_sector?: string;
  defense_breakdown?: {
    sector?: string;
    base_dice?: any[];
    terrain_bonus_dice?: any[];
    fortification_bonus_dice?: any[];
  };
  fortification?: {
    type?: string;
    bonus_dice?: any[];
  };
  attacker_effects?: {
    damage?: number;
    criticals?: any[];
    suppress?: number;
    suppression_state_after?: boolean;
  };
  defender_effects?: any;
  defender_hp_before?: number;
  defender_hp_after?: number;
  defender_killed?: boolean;
  defender_destroyed?: boolean;
  defender_suppressed?: boolean;
  suppressed?: boolean;
  killed?: boolean;
  criticals?: any[];
  resolution?: {
    remaining_damage?: number;
    remaining_criticals?: number;
    remaining_suppress?: number;
    [key: string]: any;
  };
};

type CombatEvent = {
  type: string;
  payload?: Payload;
};

type Props = {
  event: CombatEvent;
  units: Unit[];
};

function labelForUnit(unitId: string | null | undefined, units: Unit[]) {
  if (!unitId) return "Unknown";
  const unit = units.find((u) => u.id === unitId || (u as any).unit_id === unitId);
  if (unit) {
    const key = unit.unit_key || (unit as any).key;
    return unitImages[key as keyof typeof unitImages]?.label || key || unitId;
  }
  return unitId.replace(/_/g, " ");
}

const DICE_SPRITE_MAP: Record<string, Record<string, string>> = {
  BLUE: {
    "": "/assets/dice/blue_01.png",
    DAMAGE: "/assets/dice/blue_02.png",
    DEFENSE: "/assets/dice/blue_01.png",
    SHIELD: "/assets/dice/blue_01.png",
  },
  GREEN: {
    "": "/assets/dice/green_01.png",
    DAMAGE: "/assets/dice/green_02.png",
    "CRITICAL+DAMAGE": "/assets/dice/green_03.png",
    DEFENSE: "/assets/dice/green_01.png",
    SHIELD: "/assets/dice/green_01.png",
  },
  RED: {
    "": "/assets/dice/red_02.png",
    DAMAGE: "/assets/dice/red_01.png",
    "DAMAGE+DAMAGE": "/assets/dice/red_03.png",
    "CRITICAL+DAMAGE": "/assets/dice/red_04.png",
    CRITICAL: "/assets/dice/red_04.png",
  },
  YELLOW: {
    "": "/assets/dice/yellow_01.png",
    DAMAGE: "/assets/dice/yellow_02.png",
    "DAMAGE+DAMAGE": "/assets/dice/yellow_03.png",
    "CRITICAL+DAMAGE": "/assets/dice/yellow_04.png",
    CRITICAL: "/assets/dice/yellow_04.png",
    SUPPRESS: "/assets/dice/yellow_03.png",
  },
};

function normalizeFaces(faces: any): string {
  if (!faces) return "";
  const array = Array.isArray(faces) ? faces : [faces];
  return array
    .map((value) => {
      const face = String(value || "").toUpperCase();
      return face;
    })
    .filter(Boolean)
    .sort()
    .join("+");
}

function getDiceImageSrc(die: any): string | null {
  if (die == null) return null;

  if (typeof die === "string" || typeof die === "number") {
    const name = String(die).toUpperCase();
    if (name.includes("CRITICAL")) {
      return "/assets/dice/red_03.png";
    }
    if (name.includes("DAMAGE") || name.includes("HIT")) {
      return "/assets/dice/yellow_02.png";
    }
    if (name.includes("DEFENSE") || name.includes("SHIELD")) {
      return "/assets/dice/blue_01.png";
    }
    return "/assets/dice/green_01.png";
  }

  const color = String(die.color || die.side || "GREEN").toUpperCase();
  const faces = die.faces ?? die.face ?? die.value ?? die.text ?? [];
  const key = normalizeFaces(faces);
  const mapped = DICE_SPRITE_MAP[color]?.[key] || DICE_SPRITE_MAP[color]?.[""];
  if (mapped) {
    return mapped;
  }

  if (key.includes("CRITICAL")) {
    return "/assets/dice/red_03.png";
  }
  if (key.includes("DAMAGE") || key.includes("HIT")) {
    return "/assets/dice/yellow_02.png";
  }
  if (key.includes("DEFENSE") || key.includes("SHIELD")) {
    return "/assets/dice/blue_01.png";
  }
  return "/assets/dice/green_01.png";
}

function diceTooltip(die: any): string {
  if (die == null) return "Die";
  const color = String(die.color || die.side || "Die").toUpperCase();
  const faces = die.faces ?? die.face ?? die.value ?? die.text;
  const facesList = Array.isArray(faces) ? faces.join(", ") : String(faces || "Blank");
  return `${color} Die: ${facesList || "Blank"}`;
}

function renderDiceRow(dice: any[] = [], rolling = false) {
  return (
    <div className="combat-row-dice">
      {dice.length > 0 ? (
        dice.map((die, index) => {
          const tooltip = diceTooltip(die);
          const imageSrc = getDiceImageSrc(die);
          const color = String(die?.color || die?.side || "neutral").toLowerCase();

          return (
            <div
              key={index}
              className={`combat-die die-${color} ${rolling ? "rolling" : ""}`}
              title={tooltip}
            >
              {imageSrc ? (
                <img src={imageSrc} alt={tooltip} />
              ) : (
                <span style={{ fontSize: 11, fontWeight: 700 }}>{die?.value ?? "?"}</span>
              )}
            </div>
          );
        })
      ) : (
        <span style={{ fontSize: 11, color: "var(--text-muted)", fontStyle: "italic", padding: "10px 0" }}>
          None rolled
        </span>
      )}
    </div>
  );
}

export function CombatPanel({ event, units }: Props) {
  const [isVisible, setIsVisible] = useState(false);
  const [isRolling, setIsRolling] = useState(true);

  const payload = event.payload || {};
  const attackerUnit = units.find((u) => u.id === payload.attacker || (u as any).unit_id === payload.attacker);
  const defenderUnit = units.find((u) => u.id === payload.defender || (u as any).unit_id === payload.defender);

  const attackerName = labelForUnit(payload.attacker, units);
  const defenderName = labelForUnit(payload.defender, units);

  const attackDice = payload.attacker_attack_dice || payload.attack_dice || [];
  const defenseDice = payload.defender_defense_dice || payload.defense_dice || [];

  useEffect(() => {
    setIsVisible(false);
    setIsRolling(true);
    const showFrame = requestAnimationFrame(() => setIsVisible(true));
    const rollTimer = window.setTimeout(() => setIsRolling(false), 700);

    return () => {
      window.cancelAnimationFrame(showFrame);
      window.clearTimeout(rollTimer);
    };
  }, [event]);

  const defenderHpBefore = payload.defender_hp_before;
  const defenderHpAfter = payload.defender_hp_after;
  const delta =
    typeof defenderHpBefore === "number" && typeof defenderHpAfter === "number"
      ? Math.max(0, defenderHpBefore - defenderHpAfter)
      : (payload.attacker_effects?.damage ?? 0);

  const criticals = payload.attacker_effects?.criticals || payload.criticals || [];
  const defenderKilled = Boolean(
    payload.defender_killed ||
      payload.defender_destroyed ||
      payload.killed ||
      (defenderHpAfter != null && defenderHpAfter <= 0)
  );

  const isSuppressed = Boolean(
    payload.attacker_effects?.suppress ||
      payload.attacker_effects?.suppression_state_after ||
      payload.suppressed ||
      payload.defender_suppressed
  );

  const remainingDamage = payload.resolution?.remaining_damage ?? delta;
  const remainingSuppress = payload.resolution?.remaining_suppress ?? (payload.attacker_effects?.suppress ?? 0);

  const isCloseCombat = Boolean(
    payload.action?.includes("CLOSE") ||
      payload.action?.includes("ASSAULT") ||
      payload.is_close_combat ||
      payload.round_number != null
  );

  // Compute outcome summary
  const outcome = useMemo(() => {
    if (defenderKilled) {
      return {
        type: "KILLED",
        badge: "TOTAL CASUALTY (KIA)",
        badgeClass: "outcome-badge-kill",
        title: "☠️ TARGET DESTROYED",
        description: `${defenderName} suffered lethal combat damage (-${delta || 1} HP) and was completely wiped out from the battlefield.`,
      };
    }

    if (delta > 0) {
      return {
        type: "DAMAGED",
        badge: `PENETRATION: -${delta} HP`,
        badgeClass: "outcome-badge-damage",
        title: `💥 TARGET PENETRATED (-${delta} HP)`,
        description: isSuppressed
          ? `Incoming fire penetrated defensive cover! ${defenderName} sustained ${delta} HP damage (${defenderHpBefore} → ${defenderHpAfter} HP) and squad morale broke under fire (SUPPRESSED).`
          : `Incoming fire penetrated defensive cover! ${defenderName} sustained ${delta} HP damage, dropping from ${defenderHpBefore} to ${defenderHpAfter} HP.`,
      };
    }

    if (isSuppressed) {
      return {
        type: "SUPPRESSED",
        badge: "MORALE PINNED",
        badgeClass: "outcome-badge-suppressed",
        title: "⚠️ TARGET SUPPRESSED / PINNED DOWN",
        description: `Defensive dice and cover absorbed kinetic damage (0 HP lost), but the heavy volume of fire pinned down ${defenderName}. The unit is now SUPPRESSED (loses fast movement mobility and incurs reaction fire penalties).`,
      };
    }

    return {
      type: "DEFLECTED",
      badge: "NO DAMAGE SUSTAINED",
      badgeClass: "outcome-badge-deflected",
      title: "🛡️ ATTACK DEFLECTED / ABSORBED BY COVER",
      description: `Defensive dice and terrain cover completely neutralized incoming fire. ${defenderName} took 0 damage and remains at full combat effectiveness (${defenderHpAfter ?? defenderHpBefore ?? defenderUnit?.hp ?? "?"} HP).`,
    };
  }, [defenderKilled, delta, isSuppressed, defenderName, defenderHpBefore, defenderHpAfter, defenderUnit]);

  return (
    <div className={`combat-panel ${isVisible ? "combat-panel-visible" : ""}`}>
      {/* Header */}
      <div className="combat-header">
        <div className="combat-header-title">
          {isCloseCombat ? "⚔️ Close Combat / Assault" : "🏹 Ranged Engagement"}
        </div>
        <div className="combat-focus">
          <strong>{attackerName}</strong> → <strong>{defenderName}</strong>
          <br />
          <span className="combat-meta">
            {payload.distance != null ? `Distance ${payload.distance} hexes` : "Distance: Direct"}
            {payload.attack_sector ? ` · Sector: ${payload.attack_sector}` : ""}
            {payload.fortification?.type ? ` · Fortification: ${payload.fortification.type}` : ""}
          </span>
        </div>
      </div>

      {/* Dice Grid with Large Dice */}
      <div className="combat-dice-grid">
        <div className="combat-dice-col">
          <div className="combat-side-title">
            <span>ATTACK POOL</span>
            <span className="combat-pool-count">{attackDice.length} Dice</span>
          </div>
          {renderDiceRow(attackDice, isRolling)}
        </div>

        <div className="combat-dice-col">
          <div className="combat-side-title">
            <span>DEFENSE POOL</span>
            <span className="combat-pool-count">{defenseDice.length} Dice</span>
          </div>
          {renderDiceRow(defenseDice, isRolling)}
        </div>
      </div>

      {/* Target Effect Card (Clear Detailed Explanation) */}
      <div className={`combat-target-effect-card effect-${outcome.type.toLowerCase()}`}>
        <div className="effect-card-header">
          <span className="effect-card-title">{outcome.title}</span>
          <span className={`effect-card-badge ${outcome.badgeClass}`}>{outcome.badge}</span>
        </div>

        <p className="effect-card-desc">{outcome.description}</p>

        {/* Health Progression Visualizer */}
        {defenderHpBefore != null && defenderHpAfter != null && (
          <div className="effect-hp-tracker">
            <div className="effect-hp-labels">
              <span>Target Integrity:</span>
              <span>
                {defenderHpBefore} HP →{" "}
                <strong style={{ color: defenderHpAfter <= 0 ? "var(--neon-red)" : defenderHpAfter < defenderHpBefore ? "var(--neon-orange)" : "var(--neon-green)" }}>
                  {defenderHpAfter} HP
                </strong>
                {defenderKilled ? " (KIA)" : ""}
              </span>
            </div>
            <div className="effect-hp-pips">
              {Array.from({ length: Math.max(defenderHpBefore, defenderUnit?.max_hp || 4) }).map((_, i) => {
                const isLost = i >= defenderHpAfter && i < defenderHpBefore;
                const isRemaining = i < defenderHpAfter;
                return (
                  <span
                    key={i}
                    className={`effect-pip ${isLost ? "pip-lost" : isRemaining ? "pip-active" : "pip-empty"}`}
                    title={isLost ? "HP Lost in this engagement" : isRemaining ? "HP Remaining" : "Empty"}
                  >
                    {isLost ? "💔" : isRemaining ? "❤️" : "🖤"}
                  </span>
                );
              })}
            </div>
          </div>
        )}

        {/* Tactical Engagement Breakdown Footer */}
        <div className="effect-breakdown-grid">
          <div className="breakdown-item">
            <span className="breakdown-label">Uncancelled Damage:</span>
            <span className="breakdown-val" style={{ color: remainingDamage > 0 ? "var(--neon-orange)" : "var(--text-muted)" }}>
              {remainingDamage > 0 ? `${remainingDamage} Hit(s)` : "None (Blocked)"}
            </span>
          </div>

          <div className="breakdown-item">
            <span className="breakdown-label">Suppression ('X'):</span>
            <span className="breakdown-val" style={{ color: isSuppressed ? "var(--neon-yellow)" : "var(--text-muted)" }}>
              {isSuppressed ? `Applied (${remainingSuppress || 1})` : "None"}
            </span>
          </div>

          {criticals.length > 0 && (
            <div className="breakdown-item" style={{ gridColumn: "span 2" }}>
              <span className="breakdown-label">Critical Outcomes:</span>
              <span className="breakdown-val" style={{ color: "var(--neon-red)" }}>
                {criticals.map((c, i) => (typeof c === "object" ? c.name || c.effect || JSON.stringify(c) : String(c))).join(", ")}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
