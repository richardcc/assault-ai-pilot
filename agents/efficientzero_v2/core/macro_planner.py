"""
Hierarchical Macro-Strategy Planner for EfficientZero V2.

Implements Level-1 Strategic Planning:
1. Macro Posture Assessment (ASSAULT_VP, DEFENSIVE_HOLD, ZONE_SUPPRESS).
2. Unit Tactical Role Allocation (SPEARHEAD, FIRE_SUPPORT, OBJECTIVE_DEFENDER, FLANK_SCREEN).
3. Root Prior Modulation for MCTS (aligning tree search with strategic posture).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Tuple


def compute_macro_modulation_schedule(
    step_or_iter: int,
    total_steps_or_iters: int,
    schedule: str = "cosine",
    start_scale: float = 1.0,
    final_scale: float = 0.0,
    decay_fraction: float = 1.0,
) -> float:
    """
    Computes dynamic macro modulation scale for training or evaluation (Roadmap Task 2.8).
    
    Schedules:
    - 'constant': maintains start_scale indefinitely.
    - 'linear': linear decay from start_scale to final_scale.
    - 'cosine': half-period cosine decay from start_scale to final_scale.
    - 'step': abrupt transition from start_scale to final_scale at 50% decay_fraction.
    - 'off' or 'zero': returns 0.0 (Pure neural network free search).
    """
    mode = str(schedule or "cosine").strip().lower()
    if mode in {"off", "zero", "none", "disabled", "pure_neural"}:
        return 0.0
    if mode == "constant":
        return float(start_scale)
    total = max(1, int(total_steps_or_iters))
    df = max(1e-6, min(1.0, float(decay_fraction)))
    current = max(0, int(step_or_iter))
    progress = min(1.0, float(current) / max(1.0, float(total) * df))

    if mode == "linear":
        return float(start_scale + (final_scale - start_scale) * progress)
    elif mode == "cosine":
        return float(final_scale + 0.5 * (start_scale - final_scale) * (1.0 + math.cos(math.pi * progress)))
    elif mode == "step":
        return float(start_scale if progress < 0.5 else final_scale)
    return float(start_scale)



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
    unit_mutation_reasons: Dict[str, str] = field(default_factory=dict)
    unit_base_roles: Dict[str, str] = field(default_factory=dict)
    unit_mutated: Dict[str, bool] = field(default_factory=dict)
    friendly_vp_count: int = 0
    enemy_vp_count: int = 0
    neutral_vp_count: int = 0
    neural_intent_class: int | None = None
    enemy_coords: Dict[str, Tuple[int, int]] = field(default_factory=dict)
    enemy_suppressed: Dict[str, bool] = field(default_factory=dict)

    def get_role(self, unit_id: str) -> str:
        return self.unit_roles.get(str(unit_id), "ROLE_MANEUVER")

    def get_cohesion(self, unit_id: str) -> str:
        return self.unit_cohesion.get(str(unit_id), "SUPPORTED")

    def get_base_role(self, unit_id: str) -> str:
        return self.unit_base_roles.get(str(unit_id), "ROLE_MANEUVER")

    def get_mutation_reason(self, unit_id: str) -> str:
        return self.unit_mutation_reasons.get(str(unit_id), "DEFAULT_PROFILE")

    def is_mutated(self, unit_id: str) -> bool:
        return bool(self.unit_mutated.get(str(unit_id), False))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "posture": self.posture,
            "target_vp_id": self.target_vp_id,
            "target_vp_coords": list(self.target_vp_coords) if self.target_vp_coords else None,
            "unit_roles": dict(self.unit_roles),
            "unit_cohesion": dict(self.unit_cohesion),
            "unit_mutation_reasons": dict(self.unit_mutation_reasons),
            "unit_base_roles": dict(self.unit_base_roles),
            "unit_mutated": dict(self.unit_mutated),
            "friendly_vp_count": int(self.friendly_vp_count),
            "enemy_vp_count": int(self.enemy_vp_count),
            "neutral_vp_count": int(self.neutral_vp_count),
            "neural_intent_class": self.neural_intent_class,
            "enemy_coords": {k: list(v) for k, v in self.enemy_coords.items()},
            "enemy_suppressed": dict(self.enemy_suppressed),
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
        assault_boost: float = 1.35,
        support_boost: float = 1.35,
        defense_boost: float = 1.35,
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
        if not units:
            f_units = list(getattr(obs, "friendly_units", []) or [])
            for fu in f_units:
                if isinstance(fu, dict) and "side" not in fu:
                    fu["side"] = to_play
            e_units = list(getattr(obs, "enemy_units", []) or [])
            for eu in e_units:
                if isinstance(eu, dict) and "side" not in eu:
                    eu["side"] = "ENEMY" if to_play else "ENEMY"
            units = f_units + e_units
        vp_hexes = list(getattr(obs, "vp_hexes", []) or getattr(obs, "vp_cells", []) or [])
        vp_owner_by_hex = dict(getattr(obs, "vp_owner_by_hex", {}) or (getattr(obs, "board_state", {}) or {}).get("vp_owner_by_hex", {}) or {})
        terrain_cover_by_hex = dict(getattr(obs, "terrain_cover_by_hex", {}) or {})
        terrain_los_by_hex = dict(getattr(obs, "terrain_los_block_by_hex", {}) or {})
        fort_by_hex = dict(getattr(obs, "fortification_type_by_hex", {}) or {})

        if intent_logits is None:
            intent_logits = getattr(obs, "neural_intent_logits", None)
        if multi_vp_pred is None:
            multi_vp_pred = getattr(obs, "neural_multi_vp_pred", None)

        friendly_units: list[dict] = []
        enemy_units: list[dict] = []
        enemy_coords: Dict[str, Tuple[int, int]] = {}
        enemy_suppressed: Dict[str, bool] = {}

        for u in units:
            if not isinstance(u, dict) or not bool(u.get("alive", True)):
                continue
            uid = str(u.get("unit_id", "") or "")
            uq = u.get("q")
            ur = u.get("r")
            if str(u.get("side", "")) == to_play:
                friendly_units.append(u)
            else:
                enemy_units.append(u)
                if uid and isinstance(uq, int) and isinstance(ur, int):
                    enemy_coords[uid] = (int(uq), int(ur))
                    enemy_suppressed[uid] = bool(u.get("suppressed", False) or u.get("is_suppressed", False) or u.get("pinned", False))

        # 1. Count VP control
        friendly_vp = 0
        enemy_vp = 0
        neutral_vp = 0
        uncaptured_vps: list[tuple[int, int, str, float]] = []
        friendly_vp_coords: list[tuple[int, int]] = []

        for vp in vp_hexes:
            vq = vp.get("q")
            vr = vp.get("r")
            if not isinstance(vq, int) or not isinstance(vr, int):
                continue
            key = f"{vq},{vr}"
            owner = str(vp_owner_by_hex.get(key, ""))
            vp_val = float(vp.get("value", vp.get("per_turn", 2.0)) or 2.0)
            if owner == to_play:
                friendly_vp += 1
                friendly_vp_coords.append((vq, vr))
            elif owner:
                enemy_vp += 1
                uncaptured_vps.append((vq, vr, str(vp.get("vp_id", key)), vp_val))
            else:
                neutral_vp += 1
                uncaptured_vps.append((vq, vr, str(vp.get("vp_id", key)), vp_val))

        # 2. Determine Primary Target VP (Neural Intent guided when available, else strategic value/distance attraction)
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
                best_score = -999.0
                for vq, vr, vid, vval in uncaptured_vps:
                    min_u_dist = min(
                        (_hex_distance(int(u.get("q", 0)), int(u.get("r", 0)), vq, vr) for u in friendly_units),
                        default=99,
                    )
                    v_rel = max(0.25, float(vval) / 2.0)
                    score = v_rel / float(1 + max(0, min_u_dist))
                    if score > best_score:
                        best_score = score
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

        # 4. Role & Cohesion Assignment per Friendly Unit with Dynamic Mutation
        unit_roles: dict[str, str] = {}
        unit_cohesion: dict[str, str] = {}
        unit_coords: dict[str, Tuple[int, int]] = {}
        unit_mutation_reasons: dict[str, str] = {}
        unit_base_roles: dict[str, str] = {}
        unit_mutated: dict[str, bool] = {}
        rear_candidates: list[tuple[int, str]] = []

        try:
            from agents.efficientzero_v2.core.observation import _unit_feature_table
            feat_dict = _unit_feature_table()
            unit_feat_lookup = dict(feat_dict.get("table", {}) or {})
        except Exception:
            unit_feat_lookup = {}

        turn_now = int(getattr(obs, "turn", 1) or 1)
        max_turns = int(getattr(obs, "max_turns", 8) or 8)
        is_late_game = turn_now >= max(2, (2 * max_turns) // 3)
        has_vp_deficit = (friendly_vp < enemy_vp) or (friendly_vp == enemy_vp and friendly_vp == 0 and enemy_vp > 0)

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

            # Retrieve authoritative doctrine profile
            profile = u.get("doctrine_profile")
            if not isinstance(profile, dict):
                profile = unit_feat_lookup.get(ukey, {})
                if not profile:
                    for k_cand, v_cand in unit_feat_lookup.items():
                        if k_cand.upper() in ukey or ukey in k_cand.upper():
                            profile = v_cand
                            break
                if not profile:
                    profile = {}

            default_role_str = str(
                u.get("doctrine_role")
                or profile.get("default_role")
                or profile.get("canonical_role")
                or ""
            ).upper()

            is_heavy = any(k in ukey for k in ["MORTAR", "MMG", "BAZOOKA", "HMG", "BRIXIA", "30CAL", "50CAL", "MG"])
            is_recon = any(k in ukey for k in ["RECON", "SCOUT", "SNIPER", "RANGERS"])
            if default_role_str:
                base_canonical_role = default_role_str if default_role_str.startswith("ROLE_") else f"ROLE_{default_role_str}"
            elif is_heavy:
                base_canonical_role = "ROLE_FIRE_SUPPORT"
            elif is_recon:
                base_canonical_role = "ROLE_RECON"
            else:
                base_canonical_role = "ROLE_SPEARHEAD" if ("RIFLES" in ukey or "FJ" in ukey) else "ROLE_FLANK_SCREEN"

            unit_base_roles[uid] = base_canonical_role

            fallback_threshold_hp = int(profile.get("fallback_threshold_hp", 1))
            mut_rules = profile.get("mutation_rules", {})
            if isinstance(mut_rules, dict):
                allow_spearhead = bool(mut_rules.get("allow_spearhead_if_vp_deficit", True))
                allow_close_def = bool(mut_rules.get("allow_close_defense_on_flank", True))
            else:
                allow_spearhead = bool(profile.get("allow_spearhead_if_vp_deficit", True))
                allow_close_def = bool(profile.get("allow_close_defense_on_flank", True))

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

            # Hyde (2015, pp. 387-390) 50% Strength Retirement vs. BUA Desperation
            max_str = float(u.get("max_strength", 0) or profile.get("max_strength", 4) or 4)
            cur_str = float(u.get("strength", u.get("hp", max_str)) or max_str)
            cov = float(terrain_cover_by_hex.get(hex_key, 0.0) or 0.0)
            los_blk = float(terrain_los_by_hex.get(hex_key, 0.0) or 0.0)
            fort = str(fort_by_hex.get(hex_key, "") or "").lower()
            is_bua = bool(fort) or (cov >= 0.35 and los_blk >= 0.50)
            holding_vp_hex = (uq, ur) in friendly_vp_coords
            near_friendly_vp = any(_hex_distance(uq, ur, vq, vr) <= 1 for vq, vr in friendly_vp_coords)
            dist_to_target = _hex_distance(uq, ur, target_vp_coords[0], target_vp_coords[1]) if target_vp_coords else 99

            suppressed = bool(u.get("suppressed", False) or u.get("is_suppressed", False) or u.get("pinned", False))
            fallback_or_routed = bool(u.get("fallback", False) or u.get("routed", False))

            # Evaluate Dynamic Mutations in Strict Priority Order:
            # 1. Regla 2: Degradación de Moral y Supervivencia Crítica
            is_degraded = (
                fallback_or_routed
                or suppressed
                or (cur_str <= fallback_threshold_hp)
                or (max_str >= 2.0 and (cur_str / max_str) < 0.50 and not is_bua and not holding_vp_hex)
            )

            if is_degraded:
                unit_roles[uid] = "ROLE_RECOVER"
                unit_mutation_reasons[uid] = "MORALE_OR_HEALTH_DEGRADATION"
                unit_mutated[uid] = (base_canonical_role != "ROLE_RECOVER")

            # 2. Regla 3: Aislamiento / Flanqueo Inmediato de Apoyo Pesado
            elif is_heavy or base_canonical_role == "ROLE_FIRE_SUPPORT":
                has_adjacent_enemy = any(
                    _hex_distance(uq, ur, int(e.get("q", 0)), int(e.get("r", 0))) <= 1
                    for e in enemy_units
                )
                has_close_escort = (min_friend_dist <= 1)
                if has_adjacent_enemy and not has_close_escort and allow_close_def:
                    unit_roles[uid] = "ROLE_CLOSE_DEFENSE"
                    unit_mutation_reasons[uid] = "FLANKED_CLOSE_DEFENSE"
                    unit_mutated[uid] = True
                else:
                    unit_roles[uid] = "ROLE_FIRE_SUPPORT"
                    unit_mutation_reasons[uid] = "DEFAULT_PROFILE"
                    unit_mutated[uid] = False

            # 3. Regla 1: Presión Decisiva de Victoria por Déficit de VPs / Turno Tardío
            elif (has_vp_deficit or is_late_game) and uncaptured_vps and allow_spearhead:
                unit_roles[uid] = "ROLE_SPEARHEAD"
                unit_mutation_reasons[uid] = "VP_DEFICIT_PRESSURE"
                unit_mutated[uid] = (base_canonical_role != "ROLE_SPEARHEAD")

            # 4. Asignación Doctrinal Base y Convergencia de Objetivos
            elif holding_vp_hex and (friendly_vp > 0):
                unit_roles[uid] = "ROLE_OBJECTIVE_DEFENDER"
                unit_mutation_reasons[uid] = "OBJECTIVE_CONVERGENCE"
                unit_mutated[uid] = (base_canonical_role != "ROLE_OBJECTIVE_DEFENDER")
            elif target_vp_coords and dist_to_target <= 6:
                unit_roles[uid] = "ROLE_SPEARHEAD"
                unit_mutation_reasons[uid] = "OBJECTIVE_CONVERGENCE" if base_canonical_role != "ROLE_SPEARHEAD" else "DEFAULT_PROFILE"
                unit_mutated[uid] = (base_canonical_role != "ROLE_SPEARHEAD")
            elif posture == "DEFENSIVE_HOLD" and near_friendly_vp and (friendly_vp > 0):
                unit_roles[uid] = "ROLE_OBJECTIVE_DEFENDER"
                unit_mutation_reasons[uid] = "OBJECTIVE_CONVERGENCE"
                unit_mutated[uid] = (base_canonical_role != "ROLE_OBJECTIVE_DEFENDER")
            elif posture == "ASSAULT_VP" and dist_to_target <= 8:
                unit_roles[uid] = "ROLE_SPEARHEAD"
                unit_mutation_reasons[uid] = "VP_DEFICIT_PRESSURE" if base_canonical_role != "ROLE_SPEARHEAD" else "DEFAULT_PROFILE"
                unit_mutated[uid] = (base_canonical_role != "ROLE_SPEARHEAD")
            elif base_canonical_role in ["ROLE_SPEARHEAD", "ROLE_FIRE_SUPPORT", "ROLE_RECON"]:
                unit_roles[uid] = base_canonical_role
                unit_mutation_reasons[uid] = "DEFAULT_PROFILE"
                unit_mutated[uid] = False
            else:
                unit_roles[uid] = "ROLE_FLANK_SCREEN"
                unit_mutation_reasons[uid] = "DEFAULT_PROFILE"
                unit_mutated[uid] = False

            if dist_to_target > 5 and not is_heavy:
                rear_candidates.append((dist_to_target, uid))

        # Dunnigan's Force-to-Space & Tactical Reserve Doctrine:
        # When force size >= 4 and rear units exist beyond distance 5, keep 1 rear squad as ROLE_TACTICAL_RESERVE
        if len(friendly_units) >= 4 and rear_candidates:
            rear_candidates.sort(reverse=True)
            _, reserve_uid = rear_candidates[0]
            unit_roles[reserve_uid] = "ROLE_TACTICAL_RESERVE"
            unit_mutation_reasons[reserve_uid] = "TACTICAL_RESERVE"
            unit_mutated[reserve_uid] = True

        return MacroPlan(
            posture=posture,
            target_vp_id=target_vp_id,
            target_vp_coords=target_vp_coords,
            unit_roles=unit_roles,
            unit_cohesion=unit_cohesion,
            unit_coords=unit_coords,
            unit_mutation_reasons=unit_mutation_reasons,
            unit_base_roles=unit_base_roles,
            unit_mutated=unit_mutated,
            friendly_vp_count=friendly_vp,
            enemy_vp_count=enemy_vp,
            neutral_vp_count=neutral_vp,
            neural_intent_class=neural_intent_class,
            enemy_coords=enemy_coords,
            enemy_suppressed=enemy_suppressed,
        )

    def compute_action_boost(
        self,
        aid: str,
        macro_plan: MacroPlan,
        vp_owner_by_hex: Dict[str, str],
        to_play: str,
        modulation_scale: float = 1.0,
    ) -> float:
        """
        Computes the doctrine and cohesion modulation multiplier for a single action.
        """
        all_coords = dict(getattr(macro_plan, "unit_coords", {}) or {})
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
            if "ATTACK" in kind_upper or "FIRE" in kind_upper or "INDIRECT" in kind_upper or "RANGED" in kind_upper:
                # Base of Fire coordination (Roadmap Task 2.4):
                # When targeting an enemy unit defending or adjacent to a VP, apply Base of Fire boost (1.35x)
                target_id = parts[2] if len(parts) > 2 else ""
                enemy_pos = macro_plan.enemy_coords.get(target_id)
                is_bof = False
                if enemy_pos is not None:
                    if macro_plan.target_vp_coords and _hex_distance(enemy_pos[0], enemy_pos[1], macro_plan.target_vp_coords[0], macro_plan.target_vp_coords[1]) <= 1:
                        is_bof = True
                    elif any(_hex_distance(enemy_pos[0], enemy_pos[1], int(v_hex.split(",")[0]), int(v_hex.split(",")[1])) <= 1 for v_hex in vp_owner_by_hex if "," in v_hex):
                        is_bof = True
                if is_bof:
                    boost = self.support_boost * 1.35
                else:
                    boost = self.support_boost
        elif role == "ROLE_CLOSE_DEFENSE":
            # Close defense when heavy weapon is flanked without friendly escort
            if "DEFEND" in kind_upper or "OVERWATCH" in kind_upper or "FIRE" in kind_upper or "ATTACK" in kind_upper:
                boost = self.defense_boost * 1.25
            elif "MOVE" in kind_upper:
                actor_pos = all_coords.get(actor)
                other_positions = [pos for uid, pos in all_coords.items() if uid != actor]
                if actor_pos is not None and other_positions and dest_coords is not None:
                    cur_min = min(_hex_distance(actor_pos[0], actor_pos[1], ox, oy) for ox, oy in other_positions)
                    new_min = min(_hex_distance(dest_coords[0], dest_coords[1], ox, oy) for ox, oy in other_positions)
                    if new_min < cur_min:
                        boost = 1.20  # Rejoining friendly escort
                    else:
                        boost = 0.65
                else:
                    boost = 0.85
        elif role == "ROLE_RECON":
            # Recon: forward scouting, spotting and overwatch; avoid suicidal frontal assaults
            if "MOVE" in kind_upper:
                boost = self.assault_boost
            elif "OVERWATCH" in kind_upper or "DEFEND" in kind_upper:
                boost = self.defense_boost
            elif "ASSAULT" in kind_upper or "CLOSE" in kind_upper:
                boost = 0.70
        elif role == "ROLE_OBJECTIVE_DEFENDER":
            if "DEFEND" in kind_upper or "OVERWATCH" in kind_upper or "ATTACK" in kind_upper:
                boost = self.defense_boost
            elif "MOVE" in kind_upper:
                # Hyde (2015, p. 38 & p. 387) Anti-Impetuous Pursuit Guardrail:
                # Do not abandon a captured friendly VP to chase retreating enemies
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

        # Squad Coordination for Assault on VPs (Roadmap Task 2.4 - Base of Fire + Maneuver Element)
        if "ASSAULT" in kind_upper or "CLOSE" in kind_upper:
            target_id = parts[2] if len(parts) > 2 else ""
            target_pos = None
            target_is_suppressed = False
            if target_id in macro_plan.enemy_coords:
                target_pos = macro_plan.enemy_coords[target_id]
                target_is_suppressed = macro_plan.enemy_suppressed.get(target_id, False)
            elif dest_coords is not None:
                target_pos = dest_coords

            has_friendly_support = False
            if target_pos is not None:
                for other_uid, other_pos in all_coords.items():
                    if other_uid != actor and _hex_distance(other_pos[0], other_pos[1], target_pos[0], target_pos[1]) <= 1:
                        has_friendly_support = True
                        break

            # Unsuppressed solo frontal assault prohibition:
            if not target_is_suppressed and not has_friendly_support:
                boost *= 0.20  # -80% penalty for suicidal solo charge
            else:
                if target_is_suppressed:
                    boost *= 1.40  # Coordinated assault into suppressed defender (Base of Fire enabled)
                if has_friendly_support:
                    boost *= 1.20  # Combined squad assault support

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

        # Posture ASSAULT_VP modulation & sterile wandering pruning (Roadmap Task 2.2):
        if macro_plan.posture == "ASSAULT_VP":
            if "WAIT" in kind_upper or "PASS" in kind_upper or "IDLE" in kind_upper:
                boost *= 0.50  # 50% penalty on sterile passivity under assault posture
            elif is_capturing_vp or "CAPTURE" in kind_upper or (dest_coords is not None and dest_coords == macro_plan.target_vp_coords):
                # Direct capture or arrival at target VP hex receives maximum assault boost
                if role != "ROLE_SPEARHEAD":
                    boost *= 1.50
                if macro_plan.neural_intent_class == 0:
                    boost *= 1.15
            elif ("MOVE" in kind_upper or "ASSAULT" in kind_upper) and dest_coords is not None and macro_plan.target_vp_coords is not None:
                # Only assault / maneuver roles sprint towards target VP
                if role in {"ROLE_SPEARHEAD", "ROLE_MANEUVER", "ROLE_RECON", "ROLE_FLANK_SCREEN"}:
                    actor_pos = all_coords.get(actor)
                    if actor_pos is not None:
                        d_before = _hex_distance(actor_pos[0], actor_pos[1], macro_plan.target_vp_coords[0], macro_plan.target_vp_coords[1])
                        d_after = _hex_distance(dest_coords[0], dest_coords[1], macro_plan.target_vp_coords[0], macro_plan.target_vp_coords[1])
                        delta_d = d_before - d_after
                        if delta_d > 0:
                            # Moving strictly closer to VP: boost proportional to progress
                            if role != "ROLE_SPEARHEAD":
                                boost *= (1.0 + 0.35 * float(delta_d))
                            if macro_plan.neural_intent_class == 0:
                                boost *= 1.15
                        elif delta_d < 0:
                            # Moving away from target VP: 40% sterile wandering pruning
                            boost *= 0.60
                        else:
                            # Lateral shift without closing distance
                            boost *= 0.85

        if float(modulation_scale) != 1.0:
            boost = 1.0 + (boost - 1.0) * float(max(0.0, modulation_scale))
        return float(boost)

    def is_sterile_action(
        self,
        aid: str,
        macro_plan: MacroPlan,
        vp_owner_by_hex: Dict[str, str],
        to_play: str,
    ) -> bool:
        """
        Identifies whether an action represents sterile wandering, passive hesitation,
        or suicidal unsuppressed solo assault.
        """
        parts = str(aid).split(":")
        kind_upper = parts[0].upper() if parts else ""
        actor = parts[1] if len(parts) > 1 else ""

        # Task 2.4: Prohibit solo frontal assault if defender is unsuppressed and no friendly support
        if kind_upper in {"ASSAULT", "CLOSE", "CLOSE_COMBAT"}:
            dest_coords = None
            if len(parts) >= 4:
                try:
                    dest_coords = (int(parts[2]), int(parts[3]))
                except (ValueError, IndexError):
                    dest_coords = None
            elif len(parts) == 3 and "," in parts[2]:
                try:
                    dq_s, dr_s = parts[2].split(",", 1)
                    dest_coords = (int(dq_s), int(dr_s))
                except ValueError:
                    dest_coords = None

            target_id = parts[2] if len(parts) > 2 else ""
            target_pos = None
            target_is_suppressed = False
            if target_id in macro_plan.enemy_coords:
                target_pos = macro_plan.enemy_coords[target_id]
                target_is_suppressed = macro_plan.enemy_suppressed.get(target_id, False)
            elif dest_coords is not None:
                target_pos = dest_coords

            has_friendly_support = False
            if target_pos is not None:
                all_coords = dict(getattr(macro_plan, "unit_coords", {}) or {})
                for other_uid, other_pos in all_coords.items():
                    if other_uid != actor and _hex_distance(other_pos[0], other_pos[1], target_pos[0], target_pos[1]) <= 1:
                        has_friendly_support = True
                        break

            if not target_is_suppressed and not has_friendly_support:
                return True

        if macro_plan.posture != "ASSAULT_VP":
            return False
        role = macro_plan.get_role(actor)
        if kind_upper in {"WAIT", "PASS", "IDLE"}:
            return True
        if role in {"ROLE_SPEARHEAD", "ROLE_MANEUVER", "ROLE_RECON", "ROLE_FLANK_SCREEN"} and kind_upper in {"MOVE", "ASSAULT", "ADVANCE"}:
            dest_coords = None
            if len(parts) >= 4:
                try:
                    dest_coords = (int(parts[2]), int(parts[3]))
                except (ValueError, IndexError):
                    dest_coords = None
            elif len(parts) == 3 and "," in parts[2]:
                try:
                    dq_s, dr_s = parts[2].split(",", 1)
                    dest_coords = (int(dq_s), int(dr_s))
                except ValueError:
                    dest_coords = None
            if dest_coords and macro_plan.target_vp_coords:
                all_coords = dict(getattr(macro_plan, "unit_coords", {}) or {})
                actor_pos = all_coords.get(actor)
                if actor_pos:
                    d_before = _hex_distance(actor_pos[0], actor_pos[1], macro_plan.target_vp_coords[0], macro_plan.target_vp_coords[1])
                    d_after = _hex_distance(dest_coords[0], dest_coords[1], macro_plan.target_vp_coords[0], macro_plan.target_vp_coords[1])
                    if d_after > d_before:
                        return True
        return False

    def compute_vp_race_bonus(
        self,
        aid: str,
        macro_plan: MacroPlan,
        vp_owner_by_hex: Dict[str, str],
        to_play: str,
    ) -> float:
        """
        Computes the additive VP race prior bonus in [0.0, 1.5] for MCTS PUCT biasing.
        """
        if macro_plan.posture != "ASSAULT_VP" or not macro_plan.target_vp_coords:
            return 0.0
        parts = str(aid).split(":")
        kind_upper = parts[0].upper() if parts else ""
        actor = parts[1] if len(parts) > 1 else ""
        role = macro_plan.get_role(actor)
        if role not in {"ROLE_SPEARHEAD", "ROLE_MANEUVER", "ROLE_RECON", "ROLE_FLANK_SCREEN"}:
            return 0.0
        dest_coords = None
        if len(parts) >= 4:
            try:
                dest_coords = (int(parts[2]), int(parts[3]))
            except (ValueError, IndexError):
                dest_coords = None
        elif len(parts) == 3 and "," in parts[2]:
            try:
                dq_s, dr_s = parts[2].split(",", 1)
                dest_coords = (int(dq_s), int(dr_s))
            except ValueError:
                dest_coords = None

        if dest_coords and macro_plan.target_vp_coords:
            if dest_coords == macro_plan.target_vp_coords or "CAPTURE" in kind_upper:
                return 1.25  # Immediate capture / arrival on VP
            all_coords = dict(getattr(macro_plan, "unit_coords", {}) or {})
            actor_pos = all_coords.get(actor)
            if actor_pos:
                d_before = _hex_distance(actor_pos[0], actor_pos[1], macro_plan.target_vp_coords[0], macro_plan.target_vp_coords[1])
                d_after = _hex_distance(dest_coords[0], dest_coords[1], macro_plan.target_vp_coords[0], macro_plan.target_vp_coords[1])
                delta_d = d_before - d_after
                if delta_d > 0:
                    intent_mult = 1.20 if macro_plan.neural_intent_class == 0 else 1.0
                    return min(1.5, 0.40 * float(delta_d) * intent_mult)
        elif "CAPTURE" in kind_upper:
            return 1.25
        return 0.0

    def modulate_priors(
        self,
        priors_by_action: Dict[str, float],
        macro_plan: MacroPlan,
        legal_actions: List[str],
        vp_owner_by_hex: Dict[str, str],
        to_play: str,
        modulation_scale: float = 1.0,
    ) -> Dict[str, float]:
        """
        Modulates MCTS root priors according to unit strategic roles, Hyde cohesion tiers,
        50% strength recovery, anti-impetuous pursuit guardrails, and VP race assault biasing.
        Guarantees that resulting priors remain a normalized probability distribution.
        If modulation_scale == 0.0, priors are left unmodified (pure neural network mode).
        """
        if not priors_by_action or float(modulation_scale) <= 0.0:
            return priors_by_action

        adjusted: dict[str, float] = {}
        for aid in legal_actions:
            prior = float(priors_by_action.get(aid, 1e-4))
            boost = self.compute_action_boost(
                aid,
                macro_plan,
                vp_owner_by_hex,
                to_play,
                modulation_scale=float(modulation_scale),
            )
            adjusted[aid] = max(1e-6, prior * boost)

        # Normalize
        total = sum(adjusted.values())
        if total > 0.0:
            return {k: v / total for k, v in adjusted.items()}
        return priors_by_action


