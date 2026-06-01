import { useEffect, useState } from "react";
import { unitImages } from "../config/unitImages";
import { sides } from "../config/sides";

type Unit = {
  id: string;
  unit_key: string;
  side: string;
  hp?: number;
  q: number;
  r: number;
};

type Payload = {
  attacker?: string;
  defender?: string;
  attacker_attack_dice?: any[];
  attack_dice?: any[];
  defender_defense_dice?: any[];
  defense_dice?: any[];
  distance?: number;
  attack_sector?: string;
  defender_hp_before?: number;
  defender_hp_after?: number;
  defender_killed?: boolean;
  defender_destroyed?: boolean;
  killed?: boolean;
  attacker_effects?: { criticals?: any[] };
  criticals?: any[];
};

type CombatEvent = {
  type: string;
  payload?: Payload;
};

type Props = {
  event: CombatEvent;
  units: Unit[];
};

function labelForUnit(unitId?: string | null, units: Unit[]) {
  if (!unitId) return "Unknown";

  const unit = units.find((u) => u.id === unitId);
  if (unit) {
    return unitImages[unit.unit_key as keyof typeof unitImages]?.label || unit.unit_key;
  }

  return unitId;
}

const DICE_SPRITE_MAP: Record<string, Record<string, string>> = {
  BLUE: {
    "": "/assets/dice/blue_01.png",
    DAMAGE: "/assets/dice/blue_02.png",
  },
  GREEN: {
    "": "/assets/dice/green_01.png",
    DAMAGE: "/assets/dice/green_02.png",
    "CRITICAL+DAMAGE": "/assets/dice/green_03.png",
  },
  RED: {
    "": "/assets/dice/red_02.png",
    DAMAGE: "/assets/dice/red_01.png",
    "DAMAGE+DAMAGE": "/assets/dice/red_03.png",
    "CRITICAL+DAMAGE": "/assets/dice/red_04.png",
  },
  YELLOW: {
    "": "/assets/dice/yellow_01.png",
    DAMAGE: "/assets/dice/yellow_02.png",
    "DAMAGE+DAMAGE": "/assets/dice/yellow_03.png",
    "CRITICAL+DAMAGE": "/assets/dice/yellow_04.png",
  },
};

function normalizeFaces(faces: any): string {
  if (!faces) return "";
  const array = Array.isArray(faces) ? faces : [faces];
  return array
    .map((value) => {
      const face = String(value || "").toUpperCase();
      return face === "SUPPRESS" ? "CRITICAL" : face;
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

  // Fallback if the color is unknown
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

function diceLabel(d: any) {
  if (typeof d === "string" || typeof d === "number") {
    return String(d);
  }
  if (d == null) {
    return "-";
  }
  return String(d.value ?? d.face ?? d.text ?? d.label ?? JSON.stringify(d));
}

function renderDiceRow(dice: any[] = [], rolling = false) {
  return (
    <div className="combat-row">
      <div className="combat-row-dice">
        {dice.map((die, index) => {
          const text = diceLabel(die);
          const imageSrc = getDiceImageSrc(die);
          const className = [
            "combat-die",
            rolling ? "rolling" : "",
            die?.critical ? "critical" : "",
            die?.hit ? "hit" : "",
          ]
            .filter(Boolean)
            .join(" ");

          return (
            <div key={index} className={className}>
              {imageSrc ? (
                <img src={imageSrc} alt={text || "combat die"} />
              ) : (
                text
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function CombatPanel({ event, units }: Props) {
  const [isVisible, setIsVisible] = useState(false);
  const [isRolling, setIsRolling] = useState(true);

  const payload = event.payload || {};
  const attackerName = labelForUnit(payload.attacker, units);
  const defenderName = labelForUnit(payload.defender, units);

  const attackDice = payload.attacker_attack_dice || payload.attack_dice || [];
  const defenseDice = payload.defender_defense_dice || payload.defense_dice || [];

  useEffect(() => {
    setIsVisible(false);
    setIsRolling(true);
    const showFrame = requestAnimationFrame(() => setIsVisible(true));
    const rollTimer = window.setTimeout(() => setIsRolling(false), 800);

    return () => {
      window.cancelAnimationFrame(showFrame);
      window.clearTimeout(rollTimer);
    };
  }, [event]);

  const defenderHpBefore = payload.defender_hp_before;
  const defenderHpAfter = payload.defender_hp_after;
  const delta = typeof defenderHpBefore === "number" && typeof defenderHpAfter === "number"
    ? Math.max(0, defenderHpBefore - defenderHpAfter)
    : null;

  const criticals = payload.attacker_effects?.criticals || payload.criticals || [];
  const defenderKilled = payload.defender_killed || payload.defender_destroyed || payload.killed;

  return (
    <div className={`combat-panel ${isVisible ? "combat-panel-visible" : ""}`}>
      <div className="combat-header">
        <div className="combat-header-title">⚔️ Ranged Combat</div>
        <div className="combat-focus">
          <strong>{attackerName}</strong> → <strong>{defenderName}</strong>
          <br />
          <span className="combat-meta">
            {payload.distance != null ? `Distance ${payload.distance}` : "Distance N/A"}
            {payload.attack_sector ? ` · ${payload.attack_sector}` : ""}
          </span>
        </div>
      </div>

      <div className="combat-dice-grid">
        <div className="combat-dice-col">
          <div className="combat-side-title">ATTACK</div>
          {renderDiceRow(attackDice, isRolling)}
        </div>
        <div className="combat-dice-col">
          <div className="combat-side-title">DEFENSE</div>
          {renderDiceRow(defenseDice, isRolling)}
        </div>
      </div>

      <div className="combat-body">
        {delta != null && delta > 0 && (
          <div className="combat-damage">
            {defenderName}: -{delta} HP ({defenderHpBefore} → {defenderHpAfter})
          </div>
        )}

        {criticals.length > 0 && (
          <div className="combat-crit">💥 Critical hits: {criticals.length}</div>
        )}

        {defenderKilled && (
          <div className="combat-kill">☠️ {defenderName} DESTROYED</div>
        )}
      </div>
    </div>
  );
}
