from assault_model.actions.status import WaitAction
from assault_model.actions.ranged_direct import RangedDirectAttack
from assault_model.actions.ranged_indirect import RangedIndirectAttack
from assault_model.actions.composite_fire import MoveThenFireAction, FireThenMoveAction
from assault_model.actions.action_catalog import ActionCatalog
from assault_model.actions.action_category import ActionCategory


from assault_sim.rl.tactical_options import TacticalOption
from assault_sim.rl.strategic_intents import StrategicIntent
from assault_sim.config.movement_tactical_config import load_movement_tactical_config
from assault_model.map.terrain_config import terrain_config
from assault_model.map.hex_utils import safe_hex_distance
import copy


_MOVE_CFG = load_movement_tactical_config()


class OptionExecutor:
    _ALLOWED_OPTIONS_BY_STRATEGY = {
        StrategicIntent.CAPTURE: {TacticalOption.ADVANCE, TacticalOption.FLANK, TacticalOption.ATTACK},
        StrategicIntent.DENY: {TacticalOption.ADVANCE, TacticalOption.ATTACK, TacticalOption.HOLD},
        StrategicIntent.ATTRIT: {TacticalOption.ATTACK, TacticalOption.FLANK, TacticalOption.ADVANCE},
        StrategicIntent.PRESERVE: {TacticalOption.RETREAT, TacticalOption.HOLD, TacticalOption.ADVANCE},
    }


    def __init__(self, heuristic_controller, avoid_bad_trades: bool = False, adv_threshold: float = -0.5):
        self.heuristic = heuristic_controller
        # When True, block attacks whose combat advantage is below adv_threshold.
        self.avoid_bad_trades = avoid_bad_trades
        # Minimum combat advantage required to consider an attack.
        self.adv_threshold = adv_threshold
        # Position history per unit to reduce A->B->A oscillations.
        self._prev_pos_by_unit = {}
        self._prevprev_pos_by_unit = {}
        # Per-unit retreat streak guardrail.
        self._retreat_streak_by_unit = {}
        # Per-unit CAPTURE staging streak (used to break lateral loops).
        self._capture_staging_streak_by_unit = {}

    def _update_position_history(self, unit):
        if unit is None or getattr(unit, "position", None) is None:
            return
        uid = getattr(unit, "unit_id", None)
        if not uid:
            return
        pos_now = (unit.position.q, unit.position.r)
        prev = self._prev_pos_by_unit.get(uid)
        if prev != pos_now:
            self._prevprev_pos_by_unit[uid] = prev
            self._prev_pos_by_unit[uid] = pos_now

    def _is_reversal_move(self, unit, new_pos) -> bool:
        uid = getattr(unit, "unit_id", None)
        if not uid or new_pos is None:
            return False
        prevprev = self._prevprev_pos_by_unit.get(uid)
        if prevprev is None:
            return False
        return (new_pos.q, new_pos.r) == prevprev

    def _captured_objectives_for_side(self, state, side: str) -> int:
        points = getattr(getattr(state, "victory", None), "points", []) or []
        if not points or not side:
            return 0
        own_ownership = self._ownership_for_side(state, side)
        if own_ownership is None:
            return 0
        captured = 0
        for vp in points:
            hs = state.hex_states.get(vp.hex_coords)
            if hs is not None and hs.ownership == own_ownership:
                captured += 1
        return captured

    def _normalize_side_key(self, side) -> str:
        return str(getattr(side, "value", side) or "").upper()

    def _ownership_for_side(self, state, side):
        side_to_ownership = getattr(state, "side_to_ownership", {}) or {}
        key = self._normalize_side_key(side)
        if not key:
            return None
        # Primary lookup with normalized key.
        own = side_to_ownership.get(key)
        if own is not None:
            return own
        # Fallback: defensive scan if map keys are not normalized.
        for k, v in side_to_ownership.items():
            if self._normalize_side_key(k) == key:
                return v
        return None

    def _is_behind_on_objectives(self, state, side: str) -> bool:
        if not side:
            return False
        points = getattr(getattr(state, "victory", None), "points", []) or []
        if not points:
            return False
        own = self._captured_objectives_for_side(state, side)
        side_to_ownership = getattr(state, "side_to_ownership", {}) or {}
        others = [
            self._captured_objectives_for_side(state, s)
            for s in side_to_ownership.keys()
            if s != side
        ]
        best_other = max(others) if others else 0
        return own < best_other

    def _unit_group(self, unit) -> str:
        ut = getattr(unit, "unit_type", None)
        cat = getattr(ut, "category", None)
        val = str(getattr(cat, "value", "INFANTRY")).upper()
        if "VEHICLE" in val:
            return "VEHICLE"
        if "ARTILLERY" in val:
            return "ARTILLERY"
        return "INFANTRY"

    def _hex_terrain_name(self, state, pos) -> str:
        game_map = getattr(state, "game_map", None)
        if game_map is None or pos is None:
            return "clear"
        hx = game_map.get_hex(pos.q, pos.r)
        if hx is None:
            return "clear"
        return hx.get_terrain()

    def _terrain_tactical_score(self, state, unit, pos) -> float:
        terrain_name = self._hex_terrain_name(state, pos)
        group = self._unit_group(unit)
        defense_score = float(len(terrain_config.get_defense_dice(terrain_name, group)))
        los = str(terrain_config.get_los(terrain_name)).upper()
        los_bonus = 0.0
        if los == "HINDERED":
            los_bonus = 0.35
        elif los == "BLOCKED":
            los_bonus = 0.6
        return defense_score + los_bonus

    def _objective_target_hex(self, state, unit):
        points = getattr(getattr(state, "victory", None), "points", []) or []
        if not points:
            return None
        own_ownership = self._ownership_for_side(state, unit.side)
        best = None
        best_score = float("-inf")
        allies = [
            u for u in getattr(state, "units", [])
            if getattr(u, "alive", False)
            and getattr(u, "side", None) == getattr(unit, "side", None)
            and getattr(u, "position", None) is not None
            and getattr(u, "unit_id", None) != getattr(unit, "unit_id", None)
        ]
        for vp in points:
            hs = state.hex_states.get(vp.hex_coords)
            owned_by_self = hs is not None and hs.ownership == own_ownership
            # Prioritize uncaptured objectives; deprioritize already owned.
            need = 0.0 if owned_by_self else 1.0
            dist = safe_hex_distance(unit.position, vp.hex_coords)
            # Anti-congestion: avoid sending all units to the same VP lane.
            ally_pressure = sum(
                1 for a in allies if safe_hex_distance(a.position, vp.hex_coords) <= 2
            )
            score = need * 120.0 + float(getattr(vp, "per_turn", 0)) * 2.0 - float(dist)
            score -= 2.5 * float(ally_pressure)
            # If this VP is already owned and the unit is sitting on it,
            # strongly encourage rotating to another pending objective.
            if owned_by_self and dist == 0:
                score -= 6.0
            if score > best_score:
                best_score = score
                best = vp.hex_coords
        return best

    def _has_uncaptured_objective(self, state, unit) -> bool:
        points = getattr(getattr(state, "victory", None), "points", []) or []
        if not points:
            return False
        own_ownership = self._ownership_for_side(state, unit.side)
        for vp in points:
            hs = state.hex_states.get(vp.hex_coords)
            if hs is None:
                continue
            if hs.ownership != own_ownership:
                return True
        return False

    def _has_uncaptured_objective_for_side(self, state, side: str) -> bool:
        points = getattr(getattr(state, "victory", None), "points", []) or []
        if not points or not side:
            return False
        own_ownership = self._ownership_for_side(state, side)
        for vp in points:
            hs = state.hex_states.get(vp.hex_coords)
            if hs is None:
                continue
            if hs.ownership != own_ownership:
                return True
        return False

    def _is_target_on_enemy_or_neutral_vp(self, state, unit, target) -> bool:
        if target is None or getattr(target, "position", None) is None:
            return False
        points = getattr(getattr(state, "victory", None), "points", []) or []
        if not points:
            return False
        pos = (target.position.q, target.position.r)
        vp_hexes = {vp.hex_coords for vp in points}
        if pos not in vp_hexes:
            return False
        own_ownership = self._ownership_for_side(state, unit.side)
        hs = state.hex_states.get(pos)
        return hs is None or hs.ownership != own_ownership

    def _is_target_on_owned_vp(self, state, unit, target) -> bool:
        if target is None or getattr(target, "position", None) is None:
            return False
        points = getattr(getattr(state, "victory", None), "points", []) or []
        if not points:
            return False
        pos = (target.position.q, target.position.r)
        vp_hexes = {vp.hex_coords for vp in points}
        if pos not in vp_hexes:
            return False
        own_ownership = self._ownership_for_side(state, unit.side)
        hs = state.hex_states.get(pos)
        return hs is not None and hs.ownership == own_ownership

    def _is_capture_emergency(self, state, unit) -> bool:
        if unit is None:
            return False
        hp = float(getattr(unit, "hp", 0) or 0)
        max_hp = float(getattr(getattr(unit, "unit_type", None), "max_strength", 0) or 0)
        suppressed = bool(getattr(unit, "suppressed", False))
        enemies = [
            u for u in getattr(state, "units", [])
            if getattr(u, "alive", False)
            and getattr(u, "side", None) != getattr(unit, "side", None)
            and getattr(u, "position", None) is not None
            and getattr(unit, "position", None) is not None
        ]
        close_threat = any(safe_hex_distance(unit.position, e.position) <= 2 for e in enemies)
        # Be stricter with CAPTURE emergencies: avoid over-triggering retreats
        # when objectives are still pending.
        critical_hp = hp <= max(1.0, max_hp * 0.20) if max_hp > 0 else hp <= 1.0
        # Retreat in CAPTURE only under hard emergency:
        # - critical HP with nearby threat, OR
        # - suppressed and nearby threat.
        return bool((critical_hp and close_threat) or (suppressed and close_threat))

    def _best_step_into_uncaptured_vp(self, state, unit):
        if unit is None or getattr(unit, "position", None) is None:
            return None
        points = getattr(getattr(state, "victory", None), "points", []) or []
        if not points:
            return None
        own_ownership = self._ownership_for_side(state, unit.side)
        vp_hexes = {vp.hex_coords for vp in points}
        actions = ActionCatalog(state, unit, terrain_config).actions()
        best = None
        best_score = float("-inf")
        for a in actions:
            if a.action_type.category != ActionCategory.MOVEMENT:
                continue
            path = getattr(a, "path", None)
            if not path:
                continue
            new_pos = path[-1]
            pos_t = (new_pos.q, new_pos.r)
            if pos_t not in vp_hexes:
                continue
            hs = state.hex_states.get(pos_t)
            # Capture-eligible VP: currently not owned by this side.
            if hs is not None and hs.ownership == own_ownership:
                continue
            terrain_score = self._terrain_tactical_score(state, unit, new_pos)
            score = 1000.0 + terrain_score
            if score > best_score:
                best_score = score
                best = a
        return best

    def _is_uncaptured_vp_hex(self, state, side: str, pos) -> bool:
        if pos is None or not side:
            return False
        points = getattr(getattr(state, "victory", None), "points", []) or []
        if not points:
            return False
        vp_hexes = {vp.hex_coords for vp in points}
        key = (getattr(pos, "q", None), getattr(pos, "r", None))
        if key not in vp_hexes:
            return False
        own_ownership = self._ownership_for_side(state, side)
        hs = state.hex_states.get(key)
        return hs is None or hs.ownership != own_ownership

    def _nearest_uncaptured_vp_dist(self, state, unit):
        points = getattr(getattr(state, "victory", None), "points", []) or []
        if not points or unit is None or getattr(unit, "position", None) is None:
            return None
        own_ownership = self._ownership_for_side(state, unit.side)
        best = None
        for vp in points:
            hs = state.hex_states.get(vp.hex_coords)
            if hs is not None and hs.ownership == own_ownership:
                continue
            d = safe_hex_distance(unit.position, vp.hex_coords)
            if best is None or d < best:
                best = d
        return best

    def _nearest_uncaptured_vp_dist_from_pos(self, state, side: str, pos):
        points = getattr(getattr(state, "victory", None), "points", []) or []
        if not points or pos is None or not side:
            return None
        own_ownership = self._ownership_for_side(state, side)
        best = None
        for vp in points:
            hs = state.hex_states.get(vp.hex_coords)
            if hs is not None and hs.ownership == own_ownership:
                continue
            d = safe_hex_distance(pos, vp.hex_coords)
            if best is None or d < best:
                best = d
        return best

    def _best_capture_staging_move(self, state, unit):
        actions = ActionCatalog(state, unit, terrain_config).actions()
        moves = [a for a in actions if getattr(getattr(a, "action_type", None), "category", None) == ActionCategory.MOVEMENT]
        if not moves:
            return None, "no_movement_actions", None, None

        dist_before = self._nearest_uncaptured_vp_dist(state, unit)
        best_any = None
        best_any_score = float("-inf")
        best_non_worse = None
        best_non_worse_score = float("-inf")
        saw_equal = False
        saw_increase_only = True

        for m in moves:
            path = getattr(m, "path", None)
            if not path:
                continue
            end = path[-1]
            if self._is_reversal_move(unit, end) and not self._is_uncaptured_vp_hex(state, unit.side, end):
                # Hard stop to A->B->A oscillations during CAPTURE staging.
                continue
            dist_after = self._nearest_uncaptured_vp_dist_from_pos(state, unit.side, end)
            if dist_after is None:
                continue
            terrain_score = self._terrain_tactical_score(state, unit, end)
            score = -float(dist_after) + 0.3 * terrain_score
            if self._is_reversal_move(unit, end):
                score -= 8.0
            if score > best_any_score:
                best_any_score = score
                best_any = (m, dist_after, score)
            if dist_before is not None and dist_after < dist_before:
                saw_increase_only = False
                if score > best_non_worse_score:
                    best_non_worse_score = score
                    best_non_worse = (m, dist_after, score)
            elif dist_before is not None and dist_after == dist_before:
                saw_equal = True
                saw_increase_only = False
                # Allow lateral staging moves if not getting worse.
                if score > best_non_worse_score:
                    best_non_worse_score = score
                    best_non_worse = (m, dist_after, score)

        if best_non_worse is not None:
            move, dist_after, _ = best_non_worse
            if dist_before is not None and dist_after < dist_before:
                return move, "objective_progress_move", dist_before, dist_after
            if dist_before is not None and dist_after == dist_before:
                return move, "objective_staging_move", dist_before, dist_after
            return move, "objective_staging_move", dist_before, dist_after
        if best_any is not None:
            move, dist_after, _ = best_any
            if saw_increase_only and dist_before is not None:
                return move, "all_moves_increase_distance", dist_before, dist_after
            if saw_equal:
                return move, "only_equal_distance_moves", dist_before, dist_after
            return move, "no_progress_move_available", dist_before, dist_after
        return None, "no_movement_actions", dist_before, None

    def _has_vp_attack_opportunity(self, state, unit) -> bool:
        if unit is None:
            return False
        actions = ActionCatalog(state, unit, terrain_config).actions()
        attacks = [a for a in actions if self._is_attack_action(a)]
        if not attacks:
            return False
        for a in attacks:
            target = self._resolve_action_target(state, a)
            if self._is_target_on_enemy_or_neutral_vp(state, unit, target):
                return True
        return False

    def _is_attack_action(self, action) -> bool:
        return isinstance(
            action,
            (
                RangedDirectAttack,
                RangedIndirectAttack,
                MoveThenFireAction,
                FireThenMoveAction,
            ),
        )

    def _resolve_action_target(self, state, action):
        target = getattr(action, "target", None)
        if target is not None:
            return target
        target_id = getattr(action, "target_id", None)
        if target_id:
            return next(
                (u for u in getattr(state, "units", []) if getattr(u, "unit_id", None) == target_id),
                None,
            )
        return None

    def _capture_priority_action(self, state, unit, attack_mode):
        # 1) Emergency handling: allow retreat.
        if self._is_capture_emergency(state, unit):
            action = self.heuristic.choose_action(state, unit, TacticalOption.RETREAT)
            if isinstance(action, (RangedDirectAttack, RangedIndirectAttack)):
                action = WaitAction(unit.unit_id)
            if action is not None:
                action.rl_capture_fallback_reason = "capture_emergency"
                action.rl_capture_move_block_profile = "emergency_blocked"
            return action or WaitAction(unit.unit_id), TacticalOption.RETREAT

        # 2) If we can occupy an uncaptured VP now, do it immediately.
        step_into_vp = self._best_step_into_uncaptured_vp(state, unit)
        if step_into_vp is not None:
            d_before = self._nearest_uncaptured_vp_dist(state, unit)
            step_into_vp.rl_capture_fallback_reason = "step_into_uncaptured_vp"
            step_into_vp.rl_capture_move_block_profile = "step_into_uncaptured_vp"
            step_into_vp.rl_capture_target_dist_before = d_before
            step_into_vp.rl_capture_target_dist_after = 0
            return step_into_vp, TacticalOption.ADVANCE

        # 3) Evaluate movement and attacks jointly near VP.
        move, move_reason, dist_before, dist_after = self._best_capture_staging_move(state, unit)
        nearest_vp_d = self._nearest_uncaptured_vp_dist(state, unit)
        uid = getattr(unit, "unit_id", None)
        if uid and move_reason == "objective_staging_move":
            self._capture_staging_streak_by_unit[uid] = int(self._capture_staging_streak_by_unit.get(uid, 0)) + 1
        elif uid:
            self._capture_staging_streak_by_unit[uid] = 0

        # 4) Attack under tactical gate: VP pressure/defense or decent local advantage.
        actions = ActionCatalog(state, unit, terrain_config).actions()
        attacks = [
            a for a in actions
            if self._is_attack_action(a)
        ]
        # Hard anti-staging break:
        # if CAPTURE keeps staging near VP without progress, force a useful attack
        # instead of another lateral move.
        if attacks and uid:
            staging_streak = int(self._capture_staging_streak_by_unit.get(uid, 0))
            vp_dist_unknown = nearest_vp_d is None or float(nearest_vp_d) >= 999.0
            if (
                move_reason == "objective_staging_move"
                and (vp_dist_unknown or float(nearest_vp_d) <= 3.0)
                and staging_streak >= 2
            ):
                forced = self._best_attack(attacks, state=state, unit=unit)
                if forced is not None:
                    forced.rl_capture_fallback_to_attack = True
                    forced.rl_capture_fallback_reason = "forced_attack_after_staging_loop"
                    forced.rl_capture_move_block_profile = move_reason
                    forced.rl_capture_target_dist_before = dist_before
                    forced.rl_capture_target_dist_after = dist_after
                    return forced, TacticalOption.ATTACK
        if attacks:
            gated = None
            gated_score = float("-inf")
            gated_reason = ""
            for a in attacks:
                target = self._resolve_action_target(state, a)
                if target is None or not getattr(target, "alive", False):
                    continue
                adv = float(getattr(unit, "get_combat_advantage", lambda t: 0.0)(target))
                target_on_vp = self._is_target_on_enemy_or_neutral_vp(state, unit, target)
                target_threatens_owned_vp = self._is_target_on_owned_vp(state, unit, target)
                near_vp_pressure = nearest_vp_d is not None and nearest_vp_d <= 2 and adv >= -0.05

                if not (target_on_vp or target_threatens_owned_vp or near_vp_pressure or adv >= 0.25):
                    continue
                score = adv
                if target_on_vp:
                    score += 1.0
                if target_threatens_owned_vp:
                    score += 0.8
                if near_vp_pressure:
                    score += 0.5
                if score > gated_score:
                    gated_score = score
                    gated = a
                    if target_on_vp:
                        gated_reason = "attack_gate_vp_target"
                    elif target_threatens_owned_vp:
                        gated_reason = "attack_gate_defend_owned_vp"
                    elif near_vp_pressure:
                        gated_reason = "attack_gate_near_vp_pressure"
                    else:
                        gated_reason = "attack_gate_high_adv"
            if gated is not None:
                # In CAPTURE, prioritize VP progress over opportunistic fire.
                # Only take attack fallback when movement is genuinely blocked.
                should_take_attack = (
                    move_reason in {"all_moves_increase_distance", "no_progress_move_available"}
                )
                # Hard break for repeated staging loops near VP.
                if (
                    uid
                    and move_reason == "objective_staging_move"
                    and nearest_vp_d is not None
                    and nearest_vp_d <= 3
                    and int(self._capture_staging_streak_by_unit.get(uid, 0)) >= 3
                ):
                    should_take_attack = True
                if should_take_attack:
                    gated.rl_capture_fallback_to_attack = True
                    gated.rl_capture_fallback_reason = gated_reason
                    gated.rl_capture_move_block_profile = move_reason
                    gated.rl_capture_target_dist_before = dist_before
                    gated.rl_capture_target_dist_after = dist_after
                    return gated, TacticalOption.ATTACK

        # 5) Prefer movement if it does not worsen VP progress.
        if move is not None and move_reason in {"objective_progress_move", "objective_staging_move"}:
            move.rl_capture_fallback_reason = move_reason
            move.rl_capture_move_block_profile = move_reason
            move.rl_capture_target_dist_before = dist_before
            move.rl_capture_target_dist_after = dist_after
            return move, TacticalOption.ADVANCE

        # 6) If attacks are gated and movement is poor, still allow attack fallback.
        if attacks:
            best = self._best_attack(attacks, state=state, unit=unit)
            if best is not None:
                best.rl_capture_fallback_to_attack = True
                best.rl_capture_fallback_reason = "attack_gate_relaxed_fallback"
                best.rl_capture_move_block_profile = move_reason
                best.rl_capture_target_dist_before = dist_before
                best.rl_capture_target_dist_after = dist_after
                return best, TacticalOption.ATTACK

        # 7) Fallback movement / hold.
        if move is not None:
            move.rl_capture_fallback_reason = "fallback_move_even_if_no_progress"
            move.rl_capture_move_block_profile = move_reason
            move.rl_capture_target_dist_before = dist_before
            move.rl_capture_target_dist_after = dist_after
            return move, TacticalOption.ADVANCE
        hold = WaitAction(unit.unit_id)
        hold.rl_capture_fallback_reason = "no_move_no_attack_hold"
        hold.rl_capture_move_block_profile = move_reason
        return hold, TacticalOption.HOLD

    def _tag_action(self, action, option: TacticalOption, strategy: StrategicIntent | None):
        if action is None:
            return None
        # Copy only the chosen action to keep ActionCatalog cache objects immutable.
        action = copy.deepcopy(action)
        action.rl_l2_option = option.name
        action.rl_l3_strategy = strategy.name if strategy is not None else None
        if not hasattr(action, "rl_capture_fallback_to_attack"):
            action.rl_capture_fallback_to_attack = False
        if not hasattr(action, "rl_capture_fallback_reason"):
            action.rl_capture_fallback_reason = ""
        if not hasattr(action, "rl_capture_move_block_profile"):
            action.rl_capture_move_block_profile = ""
        if not hasattr(action, "rl_capture_target_dist_before"):
            action.rl_capture_target_dist_before = None
        if not hasattr(action, "rl_capture_target_dist_after"):
            action.rl_capture_target_dist_after = None
        uid = getattr(action, "unit_id", None)
        if uid:
            if option == TacticalOption.RETREAT:
                self._retreat_streak_by_unit[uid] = int(self._retreat_streak_by_unit.get(uid, 0)) + 1
            else:
                self._retreat_streak_by_unit[uid] = 0
        return action

    # -------------------------------------------------
    def execute(
        self,
        state,
        unit,
        option: TacticalOption,
        attack_mode: int | None = None,
        strategy: StrategicIntent | None = None,
        objective_tracked_side: str | None = None,
    ):

        if unit is None:
            return WaitAction("SYSTEM")
        self._update_position_history(unit)
        tracked_side_norm = self._normalize_side_key(objective_tracked_side)
        unit_side_norm = self._normalize_side_key(getattr(unit, "side", None))
        attacker_context = bool(tracked_side_norm) and unit_side_norm == tracked_side_norm
        defender_context = bool(tracked_side_norm) and unit_side_norm != tracked_side_norm

        # Mission guardrail: when objectives are still pending, avoid being stuck
        # in PRESERVE unless this unit is in a genuine emergency.
        if (
            strategy == StrategicIntent.PRESERVE
            and self._has_uncaptured_objective_for_side(state, unit.side)
            and not self._is_capture_emergency(state, unit)
            and (not tracked_side_norm or attacker_context)
        ):
            strategy = StrategicIntent.CAPTURE
        # If we're behind on objectives, force CAPTURE intent (unless emergency).
        if (
            strategy in (StrategicIntent.PRESERVE, StrategicIntent.ATTRIT, StrategicIntent.DENY)
            and self._has_uncaptured_objective_for_side(state, unit.side)
            and self._is_behind_on_objectives(state, unit.side)
            and not self._is_capture_emergency(state, unit)
            and (not tracked_side_norm or attacker_context)
        ):
            strategy = StrategicIntent.CAPTURE
        # If objectives are still pending, avoid over-defensive DENY loops and
        # push capture intent unless this unit is in a genuine emergency.
        if (
            strategy == StrategicIntent.DENY
            and self._has_uncaptured_objective_for_side(state, unit.side)
            and not self._is_capture_emergency(state, unit)
            and (not tracked_side_norm or attacker_context)
        ):
            strategy = StrategicIntent.CAPTURE
        # Scenario role guardrail:
        # if this side is the defender (not tracked in objective table),
        # avoid CAPTURE loops and bias to DENY.
        if defender_context and strategy == StrategicIntent.CAPTURE:
            strategy = StrategicIntent.DENY

        # Deterministic CAPTURE controller to avoid reward-driven local loops.
        if (
            strategy == StrategicIntent.CAPTURE
            and self._has_uncaptured_objective_for_side(state, unit.side)
        ):
            action, chosen_option = self._capture_priority_action(state, unit, attack_mode)
            return self._tag_action(action, chosen_option, strategy)

        option = self._resolve_option_for_strategy(state, unit, option, strategy)
        option = self._apply_local_role_bias(state, unit, option, strategy)

        if (
            self._has_uncaptured_objective(state, unit)
            and not self._is_capture_emergency(state, unit)
        ):
            # Hard priority: if a VP can be occupied now, do it before shooting.
            step_into_vp = self._best_step_into_uncaptured_vp(state, unit)
            if step_into_vp is not None:
                return self._tag_action(step_into_vp, TacticalOption.ADVANCE, strategy)
        # Hard temporal capture curriculum:
        # while objectives are pending, early episode/turn CAPTURE should advance
        # toward VP unless there is an emergency or a high-value VP attack.
        turn_now = int(getattr(state, "turn", 0))
        if (
            strategy == StrategicIntent.CAPTURE
            and self._has_uncaptured_objective(state, unit)
            and not self._is_capture_emergency(state, unit)
            and turn_now <= 8
            and not self._has_vp_attack_opportunity(state, unit)
        ):
            option = TacticalOption.ADVANCE
        if (
            strategy in (StrategicIntent.CAPTURE, StrategicIntent.DENY)
            and option == TacticalOption.RETREAT
            and self._has_uncaptured_objective(state, unit)
            and not self._is_capture_emergency(state, unit)
        ):
            option = TacticalOption.ADVANCE
        if (
            strategy == StrategicIntent.PRESERVE
            and option in (TacticalOption.RETREAT, TacticalOption.HOLD, TacticalOption.ADVANCE)
            and not self._is_capture_emergency(state, unit)
            and self._has_immediate_attack(state, unit)
        ):
            # Keep PRESERVE, but avoid zero-pressure loops when a legal shot exists.
            option = TacticalOption.ATTACK
        # Hard stop to retreat loops: max 1 consecutive retreat per unit.
        uid = getattr(unit, "unit_id", None)
        if (
            option == TacticalOption.RETREAT
            and uid is not None
            and int(self._retreat_streak_by_unit.get(uid, 0)) >= 1
            and self._has_uncaptured_objective(state, unit)
            and not self._is_capture_emergency(state, unit)
        ):
            option = TacticalOption.ADVANCE

        # -------------------------------------------------
        # ✅ ATTACK
        # -------------------------------------------------
        if option == TacticalOption.ATTACK:
            if (
                strategy == StrategicIntent.CAPTURE
                and self._has_uncaptured_objective(state, unit)
                and not self._is_capture_emergency(state, unit)
            ):
                nearest_vp_d = self._nearest_uncaptured_vp_dist(state, unit)
                # If close to VP and trying to camp-attack, force movement toward capture.
                if nearest_vp_d is not None and nearest_vp_d <= 2:
                    return self._tag_action(self._move_closer(state, unit), TacticalOption.ADVANCE, strategy)
            return self._tag_action(self._execute_attack(state, unit, attack_mode), option, strategy)

        # -------------------------------------------------
        if option == TacticalOption.ADVANCE:
            return self._tag_action(self._move_closer(state, unit), option, strategy)

        # -------------------------------------------------
        if option == TacticalOption.FLANK:
            return self._tag_action(self._flank_move(state, unit), option, strategy)

        # -------------------------------------------------
        # ✅ RETREAT (NO ATAQUE)
        # -------------------------------------------------
        if option == TacticalOption.RETREAT:

            action = self.heuristic.choose_action(state, unit, option)

            if isinstance(action, (RangedDirectAttack, RangedIndirectAttack)):
                return self._tag_action(WaitAction(unit.unit_id), option, strategy)

            return self._tag_action(action or WaitAction(unit.unit_id), option, strategy)

        # -------------------------------------------------
        # ✅ HOLD (MEJORADO CON FALLBACK)
        # -------------------------------------------------
        if option == TacticalOption.HOLD:

            actions = ActionCatalog(state, unit, terrain_config).actions()

            attacks = [
                a for a in actions
                if self._is_attack_action(a)
            ]

            if attacks:
                best = self._best_attack(attacks, state=state, unit=unit)
                return self._tag_action(best if best else attacks[0], option, strategy)
            # If there are relevant objectives to capture, avoid pure passivity.
            if self._objective_target_hex(state, unit) is not None:
                return self._tag_action(self._move_closer(state, unit), option, strategy)
            return self._tag_action(WaitAction(unit.unit_id), option, strategy)

        return self._tag_action(WaitAction(unit.unit_id), option, strategy)

    def _resolve_option_for_strategy(self, state, unit, option: TacticalOption, strategy: StrategicIntent | None):
        if strategy is None:
            return option
        allowed = self._ALLOWED_OPTIONS_BY_STRATEGY.get(strategy)
        if not allowed or option in allowed:
            return option

        # Strategy-constrained fallback option (deterministic).
        if strategy == StrategicIntent.CAPTURE:
            if self._has_uncaptured_objective(state, unit):
                return TacticalOption.ADVANCE
            return TacticalOption.ATTACK
        if strategy == StrategicIntent.DENY:
            return TacticalOption.ATTACK if self._has_uncaptured_objective(state, unit) else TacticalOption.HOLD
        if strategy == StrategicIntent.ATTRIT:
            return TacticalOption.ATTACK
        if strategy == StrategicIntent.PRESERVE:
            return TacticalOption.RETREAT
        return option

    def _local_role_kind(self, state, unit) -> str:
        classification = str(getattr(getattr(unit, "unit_type", None), "classification", "")).upper()
        if "INDIRECT" in classification or "SUPPORT" in classification:
            return "SUPPORT"
        enemies = [u for u in state.units if u.alive and u.side != unit.side and u.position is not None]
        if not enemies or getattr(unit, "position", None) is None:
            return "MANEUVER"
        dmin = min(safe_hex_distance(unit.position, e.position) for e in enemies)
        if dmin <= 2:
            return "ASSAULT"
        return "MANEUVER"

    def _apply_local_role_bias(self, state, unit, option: TacticalOption, strategy: StrategicIntent | None) -> TacticalOption:
        if strategy is None:
            return option
        allowed = self._ALLOWED_OPTIONS_BY_STRATEGY.get(strategy, set())
        role = self._local_role_kind(state, unit)

        preferred = option
        if role == "SUPPORT":
            if strategy in (StrategicIntent.CAPTURE, StrategicIntent.DENY, StrategicIntent.ATTRIT):
                preferred = TacticalOption.ATTACK
            elif strategy == StrategicIntent.PRESERVE:
                preferred = TacticalOption.HOLD
        elif role == "ASSAULT":
            if strategy == StrategicIntent.PRESERVE:
                preferred = TacticalOption.RETREAT
            elif strategy in (StrategicIntent.CAPTURE, StrategicIntent.ATTRIT):
                preferred = TacticalOption.ATTACK
        else:  # MANEUVER
            if strategy == StrategicIntent.CAPTURE:
                preferred = TacticalOption.ADVANCE
            elif strategy == StrategicIntent.ATTRIT:
                # Reduce passive drift under ATTRIT.
                preferred = TacticalOption.ATTACK

        if preferred in allowed:
            return preferred
        return option if option in allowed else self._resolve_option_for_strategy(state, unit, option, strategy)

    # -------------------------------------------------
    # ✅ ATTACK (MEJORADO CON FALLBACK)
    # -------------------------------------------------
    def _execute_attack(self, state, unit, attack_mode):

        actions = ActionCatalog(state, unit, terrain_config).actions()

        attacks = [
            a for a in actions
            if self._is_attack_action(a)
        ]

        if not attacks:
            return self._move_closer(state, unit)

        best = self._best_attack(attacks, state=state, unit=unit)

        # ✅ fallback crítico (SIEMPRE dispara)
        return best if best else attacks[0]

    def _has_immediate_attack(self, state, unit) -> bool:
        actions = ActionCatalog(state, unit, terrain_config).actions()
        return any(self._is_attack_action(a) for a in actions)

    # -------------------------------------------------
    def _move_closer(self, state, unit):

        actions = ActionCatalog(state, unit, terrain_config).actions()

        objective_target = self._objective_target_hex(state, unit)
        enemies = [
            u for u in state.units
            if u.side != unit.side and u.alive
        ]

        if objective_target is None and not enemies:
            return WaitAction(unit.unit_id)

        if objective_target is None:
            objective_target = min(
                enemies,
                key=lambda e: safe_hex_distance(unit.position, e.position)
            ).position

        best = None
        best_score = float("-inf")

        for a in actions:
            if a.action_type.category != ActionCategory.MOVEMENT:
                continue

            path = getattr(a, "path", None)
            if not path:
                continue

            new_pos = path[-1]
            if self._is_reversal_move(unit, new_pos) and not self._is_uncaptured_vp_hex(state, unit.side, new_pos):
                # Hard stop to immediate reversal unless it converts an uncaptured VP.
                continue
            d = safe_hex_distance(new_pos, objective_target)
            terrain_score = self._terrain_tactical_score(state, unit, new_pos)
            score = -float(d) + _MOVE_CFG.advance_terrain_weight * terrain_score
            # Small isolated VP-conversion boost:
            # when a legal move can step into an uncaptured VP, prioritize it.
            if self._is_uncaptured_vp_hex(state, unit.side, new_pos):
                score += 120.0
            if self._is_reversal_move(unit, new_pos):
                score -= 8.0

            if score > best_score:
                best = a
                best_score = score

        return best or WaitAction(unit.unit_id)

    # -------------------------------------------------
    def _flank_move(self, state, unit):

        actions = ActionCatalog(state, unit, terrain_config).actions()

        objective_target = self._objective_target_hex(state, unit)
        enemies = [
            u for u in state.units
            if u.side != unit.side and u.alive
        ]

        if objective_target is None and not enemies:
            return WaitAction(unit.unit_id)

        if objective_target is None:
            objective_target = min(
                enemies,
                key=lambda e: safe_hex_distance(unit.position, e.position)
            ).position

        best = None
        best_score = float("-inf")

        for a in actions:
            if a.action_type.category != ActionCategory.MOVEMENT:
                continue

            path = getattr(a, "path", None)
            if not path:
                continue

            new_pos = path[-1]
            if self._is_reversal_move(unit, new_pos) and not self._is_uncaptured_vp_hex(state, unit.side, new_pos):
                # Prevent flank ping-pong behavior when no net progress is made.
                continue
            dist = safe_hex_distance(new_pos, objective_target)
            terrain_score = self._terrain_tactical_score(state, unit, new_pos)

            # ✅ Siempre preferir acercarse (antes: todas las casillas a
            # >6 hex puntuaban 0 y se elegía el primer movimiento del
            # catálogo → deriva horizontal sin avanzar).
            score = -dist + _MOVE_CFG.flank_terrain_weight * terrain_score
            if self._is_reversal_move(unit, new_pos):
                score -= 8.0

            # Bonus de flanqueo: posiciones en el "anillo" de combate
            # (cerca pero sin pegarse de frente al objetivo).
            if 1 < dist <= 3:
                score += 3

            if score > best_score:
                best_score = score
                best = a

        return best or self._move_closer(state, unit)

    # -------------------------------------------------
    # ✅ TARGET SELECTION (FIX SUAVE + FALLBACK)
    # -------------------------------------------------
    def _best_attack(self, attacks, state=None, unit=None):

        best = None
        best_score = float("-inf")

        for a in attacks:

            target = self._resolve_action_target(state, a)

            if target is None or not target.alive:
                continue

            # robustly obtain the acting unit from the action object
            unit_obj = (
                getattr(a, "unit", None)
                or getattr(a, "actor", None)
                or getattr(a, "attacker", None)
                or unit
            )
            if unit_obj is None:
                continue

            adv = unit_obj.get_combat_advantage(target)
            # expected damage proxy (optional further gating)
            exp_dmg = getattr(unit_obj, "get_expected_damage", lambda t: 0.0)(target)
            hp = getattr(target, "hp", 10)
            is_move_then_fire = isinstance(a, MoveThenFireAction)
            is_fire_then_move = isinstance(a, FireThenMoveAction)

            # Composite-aware guardrail:
            # keep composite actions enabled, but avoid forcing low-quality shots.
            # If a composite shot has near-zero expected output, skip it.
            if (is_move_then_fire or is_fire_then_move) and exp_dmg <= 0.02 and hp > 2:
                continue
            if is_move_then_fire or is_fire_then_move:
                target_on_vp = (
                    state is not None
                    and unit_obj is not None
                    and self._is_target_on_enemy_or_neutral_vp(state, unit_obj, target)
                )
                # Keep composites available, but only when they are meaningfully good
                # or have direct VP impact.
                if not target_on_vp:
                    if adv < 0.25:
                        continue
                    if exp_dmg < 0.15:
                        continue

            # If configured, block attacks that look like bad trades.
            if self.avoid_bad_trades:
                # hard block for very negative advantage
                if adv < -0.3:
                    continue

                # configurable threshold: skip when advantage below threshold
                if adv < self.adv_threshold:
                    continue

                # avoid low-advantage attacks vs high-HP targets
                if adv < 0.0 and hp > 6:
                    continue

                # avoid tiny expected damage attacks (e.g., bazooka team against armored)
                if exp_dmg <= 0.05 and hp > 3:
                    continue

            score = 0

            # ✅ núcleo del scoring
            score += adv * 30

            # ✅ debilidad del enemigo
            score += (10 - hp) * 3

            # ✅ kill confirm
            if hp <= 1:
                score += 60

            # ✅ castigo a duros
            score -= hp * 2

            # ✅ sesgo ofensivo
            score += 5

            # Composite actions remain available with a tiny tie-break bonus only.
            if is_move_then_fire:
                score += 1
            elif is_fire_then_move:
                score += 0.5

            # Objective-aware priority:
            # if target is on a VP not controlled by our side, prioritize this attack.
            if state is not None and unit_obj is not None and self._is_target_on_enemy_or_neutral_vp(state, unit_obj, target):
                score += 35

            # distancia
            if hasattr(unit_obj, "position") and hasattr(target, "position"):
                dist = safe_hex_distance(unit_obj.position, target.position)

                if dist <= 2:
                    score += 3
                elif dist > 6:
                    score -= 5

            # If composite has a movement destination, prefer safer destinations.
            if state is not None and (is_move_then_fire or is_fire_then_move):
                move_path = getattr(a, "move_path", None) or []
                if move_path:
                    end = move_path[-1]
                    score += 0.2 * self._terrain_tactical_score(state, unit_obj, end)

            if score > best_score:
                best_score = score
                best = a

        # If no acceptable attack was found, fall back to the safest available attack.
        if best is not None:
            return best

        # fallback crítico: JAMÁS dejar sin ataque
        return attacks[0] if attacks else WaitAction("SYSTEM")
