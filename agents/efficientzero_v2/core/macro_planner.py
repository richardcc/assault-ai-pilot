"""
Hierarchical Macro-Strategy Planner for EfficientZero V2.

Implements Level-1 Strategic Planning:
1. Macro Posture Assessment (ASSAULT_VP, DEFENSIVE_HOLD, ZONE_SUPPRESS).
2. Unit Tactical Role Allocation (SPEARHEAD, FIRE_SUPPORT, OBJECTIVE_DEFENDER, FLANK_SCREEN).
3. Root Prior Modulation for MCTS (aligning tree search with strategic posture).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


def _hex_distance(aq: int, ar: int, bq: int, br: int) -> int:
    dq = int(aq) - int(bq)
    dr = int(ar) - int(br)
    return int((abs(dq) + abs(dr) + abs(dq + dr)) // 2)


def _parse_action(action_id: str) -> Tuple[str, str]:
    parts = str(action_id).split(":")
    kind = parts[0] if parts else ""
    actor = parts[1] if len(parts) > 1 else ""
    return kind, actor


@dataclass
class MacroPlan:
    posture: str
    target_vp_id: str
    target_vp_coords: Tuple[int, int] | None
    unit_roles: Dict[str, str] = field(default_factory=dict)
    friendly_vp_count: int = 0
    enemy_vp_count: int = 0
    neutral_vp_count: int = 0
    neural_intent_class: int | None = None

    def get_role(self, unit_id: str) -> str:
        return self.unit_roles.get(str(unit_id), "ROLE_MANEUVER")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "posture": self.posture,
            "target_vp_id": self.target_vp_id,
            "target_vp_coords": list(self.target_vp_coords) if self.target_vp_coords else None,
            "unit_roles": dict(self.unit_roles),
            "friendly_vp_count": int(self.friendly_vp_count),
            "enemy_vp_count": int(self.enemy_vp_count),
            "neutral_vp_count": int(self.neutral_vp_count),
            "neural_intent_class": self.neural_intent_class,
        }


class MacroStrategyPlanner:
    """
    Evaluates global board state and establishes a hierarchical macro plan.
    Supports both geometric heuristics and neural-guided intent (prediction_intent & multi_vp_pred),
    plus Dunnigan's Tactical Reserve (ROLE_TACTICAL_RESERVE) and Sun Tzu's Pin-and-Flank modulation.
    """

    def __init__(
        self,
        assault_boost: float = 1.25,
        support_boost: float = 1.20,
        defense_boost: float = 1.20,
    ):
        self.assault_boost = float(assault_boost)
        self.support_boost = float(support_boost)
        self.defense_boost = float(defense_boost)

    def compute_macro_plan(
        self,
        obs: Any,
        intent_logits: List[float] | None = None,
        multi_vp_pred: List[float] | None = None,
    ) -> MacroPlan:
        to_play = str(getattr(obs, "to_play", "") or "")
        units = list(getattr(obs, "units", []) or [])
        vp_hexes = list(getattr(obs, "vp_hexes", []) or [])
        vp_owner_by_hex = dict(getattr(obs, "vp_owner_by_hex", {}) or {})

        if intent_logits is None:
            intent_logits = getattr(obs, "neural_intent_logits", None)
        if multi_vp_pred is None:
            multi_vp_pred = getattr(obs, "neural_multi_vp_pred", None)

        friendly_units: list[dict] = []
        enemy_units: list[dict] = []

        for u in units:
            if not isinstance(u, dict) or not bool(u.get("alive", True)):
                continue
            if str(u.get("side", "")) == to_play:
                friendly_units.append(u)
            else:
                enemy_units.append(u)

        # 1. Count VP control
        friendly_vp = 0
        enemy_vp = 0
        neutral_vp = 0
        uncaptured_vps: list[tuple[int, int, str]] = []

        for vp in vp_hexes:
            vq = vp.get("q")
            vr = vp.get("r")
            if not isinstance(vq, int) or not isinstance(vr, int):
                continue
            key = f"{vq},{vr}"
            owner = str(vp_owner_by_hex.get(key, ""))
            if owner == to_play:
                friendly_vp += 1
            elif owner:
                enemy_vp += 1
                uncaptured_vps.append((vq, vr, str(vp.get("vp_id", key))))
            else:
                neutral_vp += 1
                uncaptured_vps.append((vq, vr, str(vp.get("vp_id", key))))

        # 2. Determine Primary Target VP (Neural Intent guided when available, else geometric)
        target_vp_id = ""
        target_vp_coords: Tuple[int, int] | None = None
        neural_intent_class: int | None = None

        if intent_logits and len(intent_logits) > 0:
            neural_intent_class = int(max(range(len(intent_logits)), key=lambda i: float(intent_logits[i])))

        if uncaptured_vps:
            if neural_intent_class is not None and len(uncaptured_vps) > 1:
                ordered_vps = sorted(uncaptured_vps, key=lambda item: str(item[2]))
                chosen_vp = ordered_vps[neural_intent_class % len(ordered_vps)]
                target_vp_coords = (chosen_vp[0], chosen_vp[1])
                target_vp_id = chosen_vp[2]
            else:
                best_dist = 999
                for vq, vr, vid in uncaptured_vps:
                    min_u_dist = min(
                        (_hex_distance(int(u.get("q", 0)), int(u.get("r", 0)), vq, vr) for u in friendly_units),
                        default=99,
                    )
                    if min_u_dist < best_dist:
                        best_dist = min_u_dist
                        target_vp_id = vid
                        target_vp_coords = (vq, vr)

        # 3. Macro Posture (modulated by neural multi_vp_pred when present)
        if friendly_vp > enemy_vp and uncaptured_vps:
            posture = "DEFENSIVE_HOLD"
        elif friendly_vp <= enemy_vp and uncaptured_vps:
            posture = "ASSAULT_VP"
        else:
            posture = "ZONE_SUPPRESS"

        if multi_vp_pred and len(multi_vp_pred) >= 4 and uncaptured_vps:
            # multi_vp_pred = [control_ratio, contested_ratio, threat_near_vp, time_pressure]
            time_pressure = float(multi_vp_pred[3])
            threat_near_vp = float(multi_vp_pred[2])
            if time_pressure > 0.75 and friendly_vp <= enemy_vp:
                posture = "ASSAULT_VP"
            elif threat_near_vp > 0.80 and friendly_vp > enemy_vp:
                posture = "DEFENSIVE_HOLD"

        # 4. Role Assignment per Friendly Unit
        unit_roles: dict[str, str] = {}
        rear_candidates: list[tuple[int, str]] = []
        for u in friendly_units:
            uid = str(u.get("unit_id", ""))
            ukey = str(u.get("unit_key", "")).upper()
            uq = int(u.get("q", 0))
            ur = int(u.get("r", 0))

            is_heavy = any(k in ukey for k in ["MORTAR", "MMG", "BAZOOKA", "HMG", "BRIXIA"])
            dist_to_target = _hex_distance(uq, ur, target_vp_coords[0], target_vp_coords[1]) if target_vp_coords else 99

            if is_heavy:
                unit_roles[uid] = "ROLE_FIRE_SUPPORT"
            elif target_vp_coords and dist_to_target <= 3:
                unit_roles[uid] = "ROLE_SPEARHEAD"
            elif friendly_vp > 0 and any(_hex_distance(uq, ur, int(vp.get("q", 0)), int(vp.get("r", 0))) <= 1
                                         for vp in vp_hexes if str(vp_owner_by_hex.get(f"{vp.get('q')},{vp.get('r')}", "")) == to_play):
                unit_roles[uid] = "ROLE_OBJECTIVE_DEFENDER"
            elif dist_to_target <= 5:
                unit_roles[uid] = "ROLE_SPEARHEAD"
            else:
                unit_roles[uid] = "ROLE_FLANK_SCREEN"
                rear_candidates.append((dist_to_target, uid))

        # Dunnigan's Force-to-Space & Tactical Reserve Doctrine:
        # When force size >= 4 and rear units exist beyond distance 5, keep 1 rear squad as ROLE_TACTICAL_RESERVE
        if len(friendly_units) >= 4 and rear_candidates:
            rear_candidates.sort(reverse=True)
            _, reserve_uid = rear_candidates[0]
            unit_roles[reserve_uid] = "ROLE_TACTICAL_RESERVE"

        return MacroPlan(
            posture=posture,
            target_vp_id=target_vp_id,
            target_vp_coords=target_vp_coords,
            unit_roles=unit_roles,
            friendly_vp_count=friendly_vp,
            enemy_vp_count=enemy_vp,
            neutral_vp_count=neutral_vp,
            neural_intent_class=neural_intent_class,
        )

    def modulate_priors(
        self,
        priors_by_action: Dict[str, float],
        macro_plan: MacroPlan,
        legal_actions: List[str],
        vp_owner_by_hex: Dict[str, str],
        to_play: str,
    ) -> Dict[str, float]:
        """
        Modulates MCTS root priors according to unit strategic roles.
        Guarantees that resulting priors remain a normalized probability distribution.
        """
        if not priors_by_action:
            return priors_by_action

        adjusted: dict[str, float] = {}

        for aid in legal_actions:
            prior = float(priors_by_action.get(aid, 1e-4))
            kind, actor = _parse_action(aid)
            kind_upper = kind.upper()
            role = macro_plan.get_role(actor)

            boost = 1.0
            if role == "ROLE_SPEARHEAD":
                if "CAPTURE" in kind_upper:
                    boost = self.assault_boost * 1.2
                elif "MOVE" in kind_upper or "ASSAULT" in kind_upper:
                    boost = self.assault_boost
            elif role == "ROLE_FIRE_SUPPORT":
                if "ATTACK" in kind_upper or "FIRE" in kind_upper or "INDIRECT" in kind_upper:
                    boost = self.support_boost
            elif role == "ROLE_OBJECTIVE_DEFENDER":
                if "DEFEND" in kind_upper or "OVERWATCH" in kind_upper or "ATTACK" in kind_upper:
                    boost = self.defense_boost
            elif role == "ROLE_FLANK_SCREEN":
                # Sun Tzu Pin-and-Flank: screen units suppress/fix enemies or maneuver on flanks
                if "ATTACK" in kind_upper or "FIRE" in kind_upper:
                    boost = 1.0 + 0.5 * (self.support_boost - 1.0)
                elif "MOVE" in kind_upper:
                    boost = 1.0 + 0.5 * (self.assault_boost - 1.0)
            elif role == "ROLE_TACTICAL_RESERVE":
                # Dunnigan Tactical Reserve: preserve cohesion and overwatch until committed
                if "OVERWATCH" in kind_upper or "DEFEND" in kind_upper or "RALLY" in kind_upper:
                    boost = self.defense_boost
                elif "MOVE" in kind_upper and macro_plan.posture == "ASSAULT_VP":
                    boost = 1.0 + 0.4 * (self.assault_boost - 1.0)

            adjusted[aid] = max(1e-6, prior * boost)

        # Normalize
        total = sum(adjusted.values())
        if total > 0.0:
            return {k: v / total for k, v in adjusted.items()}
        return priors_by_action
