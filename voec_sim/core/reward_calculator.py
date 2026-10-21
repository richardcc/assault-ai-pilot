"""
Canonical Reward Calculator and Potential-Based Reward Shaping for VOEC / EfficientZero V2.

Implements Potential-Based Reward Shaping (PBRS) as formulated by:
    Ng, A. Y., Harada, D., & Russell, S. (1999).
    "Policy invariance under reward shaping: Theory and application to reinforcement learning."
    ICML-99, pp. 278-287.

Dynamic PBRS Extensions:
    Devlin, S. M., & Kudenko, D. (2012).
    "Dynamic potential-based reward shaping."
    AAMAS-12, pp. 433-440.

Mathematical Invariants:
    1. Static / Dynamic Potential:
       F(s, t, a, s', t') = gamma * Phi(s', t') - Phi(s, t)   [non-terminal]
       F(s, t, a, s_terminal, t_terminal) = -Phi(s, t)         [terminal, setting Phi(s_term) = 0]
       Theorem 1 (Devlin & Kudenko 2012; Ng et al. 1999):
       argmax_a Q*_{M'}(s, a) = argmax_a Q*_M(s, a)
       Guaranteeing strict policy invariance while dynamically driving time-critical objectives.

    2. Turn Urgency Factor (Task 2.3):
       tau(t, T) = min(1.0, max(0.0, t / T))
       When no VPs are controlled (N_ctrl == 0):
           Psi_urgency(t, T) = exp(-lambda_urgency * tau(t, T))
           Phi(s, t) = dist_pot * Psi_urgency(t, T) + ctrl_pot
       Induces an exponential decay in state value as turns elapse without controlling VPs,
       penalizing procrastination and rewarding rapid early capture.

    3. Cumulative Paralysis / Passivity Penalty (Task 2.3):
       Penalizes friendly units that remain outside heavy/defensive cover (cover < threshold)
       without maneuvering towards target VPs or engaging in combat (firing/attacking).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple


def _hex_distance(q1: int, r1: int, q2: int, r2: int) -> int:
    """Axial hex distance between (q1, r1) and (q2, r2)."""
    dq = int(q1) - int(q2)
    dr = int(r1) - int(r2)
    return int((abs(dq) + abs(dr) + abs(dq + dr)) // 2)


@dataclass(frozen=True)
class PotentialBreakdown:
    phi_total: float
    distance_potential: float
    control_potential: float
    friendly_units_alive: int
    uncontrolled_vps_targeted: int
    controlled_vps: int
    turn_urgency_factor: float = 0.0
    turn_urgency_decay: float = 1.0
    time_scale_multiplier: float = 1.0
    contested_vps: int = 0
    contention_potential: float = 0.0


class VPPotentialCalculator:
    """
    Computes invariant potential Phi(s) and step shaping F(s, a, s') for VP capture.

    Potential Formulation:
        Phi(s, t) = ( sum_{u in FriendlyAlive} w_u / (1 + min_{vp in TargetVPs} d(u, vp)) ) * TimeModulation(t, T)
                    + beta_contested * N_{ContestedTargetVPs}
                    + B_ctrl * N_{ControlledVPs}
    """

    def __init__(
        self,
        default_unit_weight: float = 1.0,
        controlled_vp_bonus: float = 2.0,
        gamma: float = 0.997,
        shaping_scale: float = 1.0,
        urgency_decay_lambda: float = 1.2,
        paralysis_penalty_weight: float = 0.05,
        cover_threshold: float = 0.35,
        time_scaled_pbrs: bool = False,
        vp_contested_bonus: float = 0.0,
        breach_distance: int = 2,
        breach_casualty_attenuation: float = 0.40,
    ):
        self.default_unit_weight = float(default_unit_weight)
        self.controlled_vp_bonus = float(controlled_vp_bonus)
        self.gamma = float(gamma)
        self.shaping_scale = float(shaping_scale)
        self.urgency_decay_lambda = float(urgency_decay_lambda)
        self.paralysis_penalty_weight = float(paralysis_penalty_weight)
        self.cover_threshold = float(cover_threshold)
        self.time_scaled_pbrs = bool(time_scaled_pbrs)
        self.vp_contested_bonus = float(vp_contested_bonus)
        self.breach_distance = int(breach_distance)
        self.breach_casualty_attenuation = float(breach_casualty_attenuation)

    def compute_breach_casualty_factor(
        self,
        unit_coords: Tuple[int, int],
        target_vps: Sequence[Tuple[int, int]],
    ) -> float:
        """
        Computes casualty penalty attenuation factor for units in breach zone (Task 2.10).
        If min distance to any target VP <= breach_distance, returns breach_casualty_attenuation (0.40),
        reducing casualty penalty by 60%. Otherwise returns 1.0.
        """
        if not target_vps:
            return 1.0
        uq, ur = int(unit_coords[0]), int(unit_coords[1])
        min_d = min(_hex_distance(uq, ur, int(vq), int(vr)) for vq, vr in target_vps)
        if min_d <= self.breach_distance:
            return float(self.breach_casualty_attenuation)
        return 1.0

    def compute_potential(
        self,
        units: Sequence[Any],
        vp_hexes: Sequence[Dict[str, Any]],
        vp_owner_by_hex: Dict[str, str],
        side: str,
        turn: Optional[int] = None,
        max_turns: Optional[int] = None,
    ) -> PotentialBreakdown:
        """
        Computes Phi(s, t) for a specific side given the current game state and turn.
        """
        side_norm = str(side or "").strip().upper()
        if not side_norm:
            return PotentialBreakdown(0.0, 0.0, 0.0, 0, 0, 0)

        # 1. Identify friendly alive units and their positions
        friendly_alive: List[Tuple[int, int, float]] = []
        for u in units:
            if isinstance(u, dict):
                u_side = str(u.get("side", "") or "").strip().upper()
                alive = bool(u.get("alive", True))
                hp = float(u.get("hp", 1.0) or 1.0)
                q = int(u.get("q", 0) or 0)
                r = int(u.get("r", 0) or 0)
                role = str(u.get("doctrine_role", "") or "").strip().upper()
            else:
                u_side = str(getattr(u, "side", "") or "").strip().upper()
                alive = bool(getattr(u, "alive", True))
                hp = float(getattr(u, "hp", 1.0) or 1.0)
                q = int(getattr(u, "q", 0) or 0)
                r = int(getattr(u, "r", 0) or 0)
                role = str(getattr(u, "doctrine_role", "") or "").strip().upper()

            if u_side == side_norm and alive and hp > 0:
                # Doctrinal unit weighting (Spearhead units provide higher capture weight)
                w = self.default_unit_weight
                if "SPEARHEAD" in role:
                    w *= 1.25
                friendly_alive.append((q, r, w))

        if not friendly_alive or not vp_hexes:
            return PotentialBreakdown(0.0, 0.0, 0.0, len(friendly_alive), 0, 0)

        # 2. Partition VPs into controlled vs target (contested / neutral / enemy)
        target_vps: List[Tuple[int, int, float]] = []
        controlled_vp_count = 0
        controlled_vp_weight = 0.0

        for vp in vp_hexes:
            vq = int(vp.get("q", 0) or 0)
            vr = int(vp.get("r", 0) or 0)
            key = f"{vq},{vr}"
            owner = str(vp_owner_by_hex.get(key, "") or "").strip().upper()
            val = float(vp.get("value", vp.get("per_turn", 2.0)) or 2.0)
            # Relative value scaling: normalized against baseline 2.0 VP
            # (e.g. 2 VP standard -> 1.0; 3 VP key objective -> 1.5; 4 VP -> 2.0)
            v_rel = max(0.25, val / 2.0)
            if owner == side_norm:
                controlled_vp_count += 1
                controlled_vp_weight += v_rel
            else:
                target_vps.append((vq, vr, v_rel))

        # 3. Compute distance potential towards target VPs
        dist_pot = 0.0
        if target_vps:
            for uq, ur, w in friendly_alive:
                best_attraction = max(
                    (v_rel / float(1 + max(0, _hex_distance(uq, ur, tq, tr))))
                    for tq, tr, v_rel in target_vps
                )
                dist_pot += w * best_attraction
        else:
            # All VPs controlled: friendly units maintain defensive perimeter
            for uq, ur, w in friendly_alive:
                best_attraction = max(
                    ((max(0.25, float(vp.get("value", vp.get("per_turn", 2.0)) or 2.0) / 2.0)) /
                     float(1 + max(0, _hex_distance(uq, ur, int(vp.get("q", 0)), int(vp.get("r", 0))))))
                    for vp in vp_hexes
                )
                dist_pot += (0.5 * w) * best_attraction

        # 4. Turn Urgency Factor & Dynamic PBRS Time Scaling (Task 2.3 & Task 2.10)
        turn_urgency_factor = 0.0
        turn_urgency_decay = 1.0
        time_scale_multiplier = 1.0
        if turn is not None and max_turns is not None and max_turns > 0:
            turn_now = max(0, int(turn))
            max_t = max(1, int(max_turns))
            turn_urgency_factor = min(1.0, max(0.0, float(turn_now) / float(max_t)))
            if self.time_scaled_pbrs:
                # Task 2.10: Dynamic PBRS time scaling: alpha * (1 + t / T_max)
                time_scale_multiplier = 1.0 + turn_urgency_factor
                dist_pot *= time_scale_multiplier
            else:
                # Task 2.3: When friendly side controls zero VPs, distance potential decays exponentially with t/T
                if controlled_vp_count == 0:
                    turn_urgency_decay = math.exp(-self.urgency_decay_lambda * turn_urgency_factor)
                    dist_pot *= turn_urgency_decay

        # 5. Contested VPs bonus (Task 2.10): beta * Contest
        contested_vps_count = 0
        contention_pot = 0.0
        if target_vps and friendly_alive:
            for vq, vr, _ in target_vps:
                if any(_hex_distance(uq, ur, vq, vr) <= self.breach_distance for uq, ur, _ in friendly_alive):
                    contested_vps_count += 1
            contention_pot = float(contested_vps_count) * self.vp_contested_bonus

        # 6. Control potential weighted by intrinsic VP value
        ctrl_pot = float(controlled_vp_weight) * self.controlled_vp_bonus

        total_phi = dist_pot + contention_pot + ctrl_pot
        return PotentialBreakdown(
            phi_total=float(total_phi),
            distance_potential=float(dist_pot),
            control_potential=float(ctrl_pot),
            friendly_units_alive=len(friendly_alive),
            uncontrolled_vps_targeted=len(target_vps),
            controlled_vps=controlled_vp_count,
            turn_urgency_factor=float(turn_urgency_factor),
            turn_urgency_decay=float(turn_urgency_decay),
            time_scale_multiplier=float(time_scale_multiplier),
            contested_vps=int(contested_vps_count),
            contention_potential=float(contention_pot),
        )

    def compute_paralysis_penalty(
        self,
        before_units: Sequence[Any],
        after_units: Sequence[Any],
        target_vps: Sequence[Tuple[int, int]],
        controlled_vp_coords: Sequence[Tuple[int, int]],
        terrain_cover_by_hex: Optional[Dict[str, float]],
        side: str,
        action_kind: Optional[str] = None,
        actor_unit_id: Optional[str] = None,
        damage_dealt: float = 0.0,
        passivity_tracker: Optional[Dict[str, int]] = None,
    ) -> Tuple[float, int, Dict[str, int]]:
        """
        Computes cumulative passivity / paralysis penalty for units that remain
        outside cover without maneuvering toward objectives or firing.

        Returns (penalty_value, passive_units_count, updated_streaks).
        """
        side_norm = str(side or "").strip().upper()
        if not side_norm or not after_units:
            return 0.0, 0, passivity_tracker or {}

        before_positions: Dict[str, Tuple[int, int]] = {}
        for u in before_units:
            uid = str(u.get("unit_id") if isinstance(u, dict) else getattr(u, "unit_id", ""))
            q = int(u.get("q", 0) if isinstance(u, dict) else getattr(u, "q", 0))
            r = int(u.get("r", 0) if isinstance(u, dict) else getattr(u, "r", 0))
            if uid:
                before_positions[uid] = (q, r)

        act_upper = str(action_kind or "").upper()
        is_combat_action = any(k in act_upper for k in ["FIRE", "ATTACK", "OPPORTUNITY", "BOMB"])

        total_penalty = 0.0
        passive_count = 0
        tracker = passivity_tracker if passivity_tracker is not None else {}

        controlled_set = set(controlled_vp_coords)

        for u in after_units:
            if isinstance(u, dict):
                u_side = str(u.get("side", "") or "").strip().upper()
                alive = bool(u.get("alive", True))
                hp = float(u.get("hp", 1.0) or 1.0)
                q = int(u.get("q", 0) or 0)
                r = int(u.get("r", 0) or 0)
                uid = str(u.get("unit_id", "") or "")
            else:
                u_side = str(getattr(u, "side", "") or "").strip().upper()
                alive = bool(getattr(u, "alive", True))
                hp = float(getattr(u, "hp", 1.0) or 1.0)
                q = int(getattr(u, "q", 0) or 0)
                r = int(getattr(u, "r", 0) or 0)
                uid = str(getattr(u, "unit_id", "") or "")

            if u_side != side_norm or not alive or hp <= 0 or not uid:
                continue

            hex_key = f"{q},{r}"
            cov = float((terrain_cover_by_hex or {}).get(hex_key, 0.0) or 0.0)
            is_outside_cover = cov < self.cover_threshold
            is_on_friendly_vp = (q, r) in controlled_set

            is_actor = (not actor_unit_id) or (str(actor_unit_id) == str(uid))
            did_fire = (is_combat_action and is_actor) or (float(damage_dealt) > 0.0 and is_actor)

            did_advance = False
            if target_vps:
                d_after = min(_hex_distance(q, r, tq, tr) for tq, tr in target_vps)
                if uid in before_positions:
                    bq, br = before_positions[uid]
                    d_before = min(_hex_distance(bq, br, tq, tr) for tq, tr in target_vps)
                    if d_after < d_before:
                        did_advance = True
            else:
                # All VPs already controlled: maintaining perimeter is sufficient
                did_advance = True

            # Check paralysis condition: in open ground, without shooting or advancing, not on VP
            if is_outside_cover and not is_on_friendly_vp and not did_fire and not did_advance:
                streak = tracker.get(uid, 0) + 1
                tracker[uid] = streak
                # Cumulative scaling: increases by +50% for each consecutive passive turn (up to 4x)
                unit_pen = self.paralysis_penalty_weight * (1.0 + 0.5 * min(4, streak - 1))
                total_penalty += unit_pen
                passive_count += 1
            else:
                # Unit broke passivity: reset streak
                tracker[uid] = 0

        return -float(total_penalty), passive_count, tracker

    def compute_step_shaping(
        self,
        before_units: Sequence[Any],
        after_units: Sequence[Any],
        vp_hexes: Sequence[Dict[str, Any]],
        before_vp_owner: Dict[str, str],
        after_vp_owner: Dict[str, str],
        side: str,
        done: bool,
        custom_gamma: Optional[float] = None,
        custom_scale: Optional[float] = None,
        turn_before: Optional[int] = None,
        turn_after: Optional[int] = None,
        max_turns: Optional[int] = None,
        terrain_cover_by_hex: Optional[Dict[str, float]] = None,
        action_kind: Optional[str] = None,
        actor_unit_id: Optional[str] = None,
        damage_dealt: float = 0.0,
        passivity_tracker: Optional[Dict[str, int]] = None,
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Computes F(s, t, a, s', t') = gamma * Phi(s', t') - Phi(s, t).
        When done=True, Phi(s') = 0.0, ensuring telescoping invariance.
        Also calculates cumulative paralysis penalties for exposed passive units.
        """
        gamma = float(self.gamma if custom_gamma is None else custom_gamma)
        scale = float(self.shaping_scale if custom_scale is None else custom_scale)

        b_pot = self.compute_potential(
            before_units,
            vp_hexes,
            before_vp_owner,
            side,
            turn=turn_before,
            max_turns=max_turns,
        )
        phi_before = b_pot.phi_total

        if done:
            # Ng et al. (1999): Terminal state potential is strictly 0.0
            phi_after = 0.0
            a_pot = PotentialBreakdown(0.0, 0.0, 0.0, 0, 0, 0)
        else:
            a_pot = self.compute_potential(
                after_units,
                vp_hexes,
                after_vp_owner,
                side,
                turn=turn_after if turn_after is not None else turn_before,
                max_turns=max_turns,
            )
            phi_after = a_pot.phi_total

        f_shaping = (gamma * phi_after) - phi_before
        scaled_shaping = f_shaping * scale

        # Compute paralysis penalty for exposed passive units (Task 2.3)
        paralysis_penalty = 0.0
        paralysis_count = 0
        if terrain_cover_by_hex is not None and not done:
            side_norm = str(side or "").strip().upper()
            target_vps: List[Tuple[int, int]] = []
            controlled_vp_coords: List[Tuple[int, int]] = []
            for vp in vp_hexes:
                vq = int(vp.get("q", 0) or 0)
                vr = int(vp.get("r", 0) or 0)
                key = f"{vq},{vr}"
                owner = str(after_vp_owner.get(key, "") or "").strip().upper()
                if owner == side_norm:
                    controlled_vp_coords.append((vq, vr))
                else:
                    target_vps.append((vq, vr))

            paralysis_penalty, paralysis_count, _ = self.compute_paralysis_penalty(
                before_units=before_units,
                after_units=after_units,
                target_vps=target_vps,
                controlled_vp_coords=controlled_vp_coords,
                terrain_cover_by_hex=terrain_cover_by_hex,
                side=side,
                action_kind=action_kind,
                actor_unit_id=actor_unit_id,
                damage_dealt=damage_dealt,
                passivity_tracker=passivity_tracker,
            )

        total_step_reward = scaled_shaping + paralysis_penalty

        meta = {
            "phi_before": float(phi_before),
            "phi_after": float(phi_after),
            "f_shaping_raw": float(f_shaping),
            "f_shaping_scaled": float(scaled_shaping),
            "pbrs_shaping": float(f_shaping),
            "dist_pot_before": float(b_pot.distance_potential),
            "dist_pot_after": float(a_pot.distance_potential),
            "ctrl_pot_before": float(b_pot.control_potential),
            "ctrl_pot_after": float(a_pot.control_potential),
            "turn_urgency_factor_before": float(b_pot.turn_urgency_factor),
            "turn_urgency_factor_after": float(a_pot.turn_urgency_factor),
            "turn_urgency_decay_before": float(b_pot.turn_urgency_decay),
            "turn_urgency_decay_after": float(a_pot.turn_urgency_decay),
            "time_scale_multiplier_before": float(b_pot.time_scale_multiplier),
            "time_scale_multiplier_after": float(a_pot.time_scale_multiplier),
            "contested_vps_before": int(b_pot.contested_vps),
            "contested_vps_after": int(a_pot.contested_vps),
            "contention_pot_before": float(b_pot.contention_potential),
            "contention_pot_after": float(a_pot.contention_potential),
            "paralysis_penalty": float(paralysis_penalty),
            "paralysis_units_count": int(paralysis_count),
            "gamma": float(gamma),
        }
        return float(total_step_reward), meta
