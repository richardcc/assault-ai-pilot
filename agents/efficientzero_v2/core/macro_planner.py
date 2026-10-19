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
    unit_cohesion: Dict[str, str] = field(default_factory=dict)
    unit_coords: Dict[str, Tuple[int, int]] = field(default_factory=dict)
    friendly_vp_count: int = 0
    enemy_vp_count: int = 0
    neutral_vp_count: int = 0
    neural_intent_class: int | None = None

    def get_role(self, unit_id: str) -> str:
        return self.unit_roles.get(str(unit_id), "ROLE_MANEUVER")

    def get_cohesion(self, unit_id: str) -> str:
        return self.unit_cohesion.get(str(unit_id), "SUPPORTED")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "posture": self.posture,
            "target_vp_id": self.target_vp_id,
            "target_vp_coords": list(self.target_vp_coords) if self.target_vp_coords else None,
            "unit_roles": dict(self.unit_roles),
            "unit_cohesion": dict(self.unit_cohesion),
            "friendly_vp_count": int(self.friendly_vp_count),
            "enemy_vp_count": int(self.enemy_vp_count),
            "neutral_vp_count": int(self.neutral_vp_count),
            "neural_intent_class": self.neural_intent_class,
        }


class MacroStrategyPlanner:
    """
    Evaluates global board state and establishes a hierarchical macro plan.
    Supports:
    - Geometric heuristics + neural-guided intent (prediction_intent & multi_vp_pred)
    - Dunnigan's Tactical Reserve (ROLE_TACTICAL_RESERVE)
    - Sun Tzu's Pin-and-Flank modulation (ROLE_FLANK_SCREEN)
    - Henry Hyde's (2015) Proximity Cohesion Tiers (SUPPORTED / FRIENDS_CLOSE / ISOLATED),
      50% Strength Retirement vs. BUA Desperation (ROLE_RECOVER), and Anti-Pursuit Guardrail.
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
        terrain_cover_by_hex = dict(getattr(obs, "terrain_cover_by_hex", {}) or {})
        terrain_los_by_hex = dict(getattr(obs, "terrain_los_block_by_hex", {}) or {})
        fort_by_hex = dict(getattr(obs, "fortification_type_by_hex", {}) or {})

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
        friendly_vp_coords: list[tuple[int, int]] = []

        for vp in vp_hexes:
            vq = vp.get("q")
            vr = vp.get("r")
            if not isinstance(vq, int) or not isinstance(vr, int):
                continue
            key = f"{vq},{vr}"
            owner = str(vp_owner_by_hex.get(key, ""))
            if owner == to_play:
                friendly_vp += 1
                friendly_vp_coords.append((vq, vr))
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

        # 4. Role & Cohesion Assignment per Friendly Unit
        unit_roles: dict[str, str] = {}
        unit_cohesion: dict[str, str] = {}
        unit_coords: dict[str, Tuple[int, int]] = {}
        rear_candidates: list[tuple[int, str]] = []

        # Good-order friendly positions for Hyde's SUPPORTED / ISOLATED check (pp. 389-391)
        good_order_coords = [
            (int(u.get("q", 0)), int(u.get("r", 0)), str(u.get("unit_id", "")))
            for u in friendly_units
            if not bool(u.get("routed", False)) and not bool(u.get("fallback", False))
        ]

        for u in friendly_units:
            uid = str(u.get("unit_id", ""))
            ukey = str(u.get("unit_key", "")).upper()
            uq = int(u.get("q", 0))
            ur = int(u.get("r", 0))
            unit_coords[uid] = (uq, ur)
            hex_key = f"{uq},{ur}"

            # Hyde (2015, p. 391) Proximity Cohesion Tiers: SUPPORTED (<=3), FRIENDS_CLOSE (<=6), ISOLATED (>6)
            other_dists = [
                _hex_distance(uq, ur, oq, or_)
                for oq, or_, ouid in good_order_coords
                if ouid != uid
            ]
            min_friend_dist = min(other_dists, default=99)
            if len(friendly_units) <= 1 or min_friend_dist <= 3:
                unit_cohesion[uid] = "SUPPORTED"
            elif min_friend_dist <= 6:
                unit_cohesion[uid] = "FRIENDS_CLOSE"
            else:
                unit_cohesion[uid] = "ISOLATED"

            # Hyde (2015, pp. 387-390) 50% Strength Retirement vs. BUA (Built-Up Area) Desperation
            max_str = float(u.get("max_strength", 0) or 0)
            cur_str = float(u.get("strength", max_str) or max_str)
            cov = float(terrain_cover_by_hex.get(hex_key, 0.0) or 0.0)
            los_blk = float(terrain_los_by_hex.get(hex_key, 0.0) or 0.0)
            fort = str(fort_by_hex.get(hex_key, "") or "").lower()
            is_bua = bool(fort) or (cov >= 0.35 and los_blk >= 0.50)
            holding_vp_hex = (uq, ur) in friendly_vp_coords
            near_friendly_vp = any(_hex_distance(uq, ur, vq, vr) <= 1 for vq, vr in friendly_vp_coords)

            if max_str >= 2.0 and (cur_str / max_str) < 0.50 and not is_bua and not holding_vp_hex:
                unit_roles[uid] = "ROLE_RECOVER"
                continue

            is_heavy = any(k in ukey for k in ["MORTAR", "MMG", "BAZOOKA", "HMG", "BRIXIA"])
            dist_to_target = _hex_distance(uq, ur, target_vp_coords[0], target_vp_coords[1]) if target_vp_coords else 99

            if is_heavy:
                unit_roles[uid] = "ROLE_FIRE_SUPPORT"
            elif holding_vp_hex and (friendly_vp > 0):
                unit_roles[uid] = "ROLE_OBJECTIVE_DEFENDER"
            elif target_vp_coords and dist_to_target <= 6:
                unit_roles[uid] = "ROLE_SPEARHEAD"
            elif posture == "DEFENSIVE_HOLD" and near_friendly_vp and (friendly_vp > 0):
                unit_roles[uid] = "ROLE_OBJECTIVE_DEFENDER"
            elif posture == "ASSAULT_VP" and dist_to_target <= 8:
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
            unit_cohesion=unit_cohesion,
            unit_coords=unit_coords,
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
        Modulates MCTS root priors according to unit strategic roles, Hyde cohesion tiers,
        50% strength recovery, and anti-impetuous pursuit guardrails.
        Guarantees that resulting priors remain a normalized probability distribution.
        """
        if not priors_by_action:
            return priors_by_action

        adjusted: dict[str, float] = {}
        all_coords = dict(getattr(macro_plan, "unit_coords", {}) or {})

        for aid in legal_actions:
            prior = float(priors_by_action.get(aid, 1e-4))
            parts = str(aid).split(":")
            kind = parts[0] if parts else ""
            actor = parts[1] if len(parts) > 1 else ""
            kind_upper = kind.upper()
            role = macro_plan.get_role(actor)
            cohesion = macro_plan.get_cohesion(actor)

            dest_coords: Tuple[int, int] | None = None
            if len(parts) >= 4:
                try:
                    dest_coords = (int(parts[2]), int(parts[3]))
                except (ValueError, IndexError):
                    dest_coords = None
            elif len(parts) == 3:
                dest_part = parts[2]
                if "," in dest_part:
                    try:
                        dq_s, dr_s = dest_part.split(",", 1)
                        dest_coords = (int(dq_s), int(dr_s))
                    except ValueError:
                        dest_coords = None

            is_capturing_vp = False
            if dest_coords is not None:
                vp_dest_key = f"{dest_coords[0]},{dest_coords[1]}"
                if vp_dest_key in vp_owner_by_hex:
                    vp_curr_owner = str(vp_owner_by_hex.get(vp_dest_key, "") or "").strip().upper()
                    if vp_curr_owner != str(to_play or "").strip().upper():
                        is_capturing_vp = True
                elif macro_plan.target_vp_coords == dest_coords:
                    is_capturing_vp = True

            boost = 1.0
            if role == "ROLE_SPEARHEAD":
                if is_capturing_vp or "CAPTURE" in kind_upper:
                    boost = self.assault_boost * 1.5
                elif "MOVE" in kind_upper or "ASSAULT" in kind_upper:
                    if dest_coords is not None and macro_plan.target_vp_coords is not None:
                        actor_pos = all_coords.get(actor)
                        if actor_pos is not None:
                            d_before = _hex_distance(actor_pos[0], actor_pos[1], macro_plan.target_vp_coords[0], macro_plan.target_vp_coords[1])
                            d_after = _hex_distance(dest_coords[0], dest_coords[1], macro_plan.target_vp_coords[0], macro_plan.target_vp_coords[1])
                            if d_after < d_before:
                                boost = self.assault_boost * 1.25
                            else:
                                boost = self.assault_boost
                        else:
                            boost = self.assault_boost
                    else:
                        boost = self.assault_boost
            elif role == "ROLE_FIRE_SUPPORT":
                if "ATTACK" in kind_upper or "FIRE" in kind_upper or "INDIRECT" in kind_upper:
                    boost = self.support_boost
            elif role == "ROLE_OBJECTIVE_DEFENDER":
                if "DEFEND" in kind_upper or "OVERWATCH" in kind_upper or "ATTACK" in kind_upper:
                    boost = self.defense_boost
                elif "MOVE" in kind_upper and macro_plan.posture == "DEFENSIVE_HOLD":
                    # Hyde (2015, p. 38 & p. 387) Anti-Impetuous Pursuit Guardrail:
                    # Do not abandon a captured friendly VP to chase retreating enemies when defending
                    actor_pos = all_coords.get(actor)
                    if actor_pos is not None and str(vp_owner_by_hex.get(f"{actor_pos[0]},{actor_pos[1]}", "")) == to_play:
                        boost = 0.65
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
            elif role == "ROLE_RECOVER":
                # Hyde (2015, p. 390): Unit below 50% strength outside BUA retires/rallies in good order
                if "RALLY" in kind_upper or "RECOVER" in kind_upper or "DEFEND" in kind_upper or "OVERWATCH" in kind_upper:
                    boost = self.defense_boost * 1.15
                elif "ASSAULT" in kind_upper or "CLOSE" in kind_upper:
                    boost = 0.60

            # Hyde (2015, p. 391) Anti-Isolation Cohesion Modulation:
            if cohesion == "ISOLATED" and "MOVE" in kind_upper and dest_coords is not None and len(all_coords) > 1:
                actor_pos = all_coords.get(actor)
                other_positions = [pos for uid, pos in all_coords.items() if uid != actor]
                if actor_pos is not None and other_positions:
                    cur_min = min(_hex_distance(actor_pos[0], actor_pos[1], ox, oy) for ox, oy in other_positions)
                    new_min = min(_hex_distance(dest_coords[0], dest_coords[1], ox, oy) for ox, oy in other_positions)
                    if new_min < cur_min:
                        boost *= 1.15  # Reward rejoining friendly support radius
                    elif new_min > cur_min:
                        boost *= 0.80  # Penalize wandering deeper into isolation

            adjusted[aid] = max(1e-6, prior * boost)

        # Normalize
        total = sum(adjusted.values())
        if total > 0.0:
            return {k: v / total for k, v in adjusted.items()}
        return priors_by_action

