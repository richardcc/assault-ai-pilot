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


    def __init__(
        self,
        heuristic_controller,
        avoid_bad_trades: bool = False,
        adv_threshold: float = -0.5,
        capture_guardrails_enabled: bool = True,
        diagnostic_force_capture_only: bool = False,
    ):
        self.heuristic = heuristic_controller
        # When True, block attacks whose combat advantage is below adv_threshold.
        self.avoid_bad_trades = avoid_bad_trades
        # Minimum combat advantage required to consider an attack.
        self.adv_threshold = adv_threshold
        self.capture_guardrails_enabled = bool(capture_guardrails_enabled)
        self.diagnostic_force_capture_only = bool(diagnostic_force_capture_only)
        # Position history per unit to reduce A->B->A oscillations.
        self._prev_pos_by_unit = {}
        self._prevprev_pos_by_unit = {}
        # Per-unit retreat streak guardrail.
        self._retreat_streak_by_unit = {}
        # Per-unit CAPTURE staging streak (used to break lateral loops).
        self._capture_staging_streak_by_unit = {}
        # Per-unit streak of near-VP states without legal step-in.
        self._capture_no_stepin_near_streak_by_unit = {}
        # Anti-spam throttle for opening-window forced attacks.
        self._capture_open_window_last_seq_by_unit = {}
        self._capture_decision_seq = 0
        # Monotonic step id to trace plan evolution.
        self._plan_step_seq = 0
        # P4.3c: lightweight per-turn capture budget (side, turn) -> counters.
        self._capture_budget_by_side_turn = {}
        self._capture_budget_required_advances = 2
        # Per-state action catalog cache to avoid repeated legal-path recomputation.
        self._action_catalog_cache_state_key = None
        self._action_catalog_cache = {}
        # Short-lived CAPTURE focus lock to reduce VP target ping-pong.
        self._capture_focus_lock_by_unit = {}
        self._capture_focus_ttl_steps = 3

    def _capture_budget_key(self, side, turn_now: int) -> tuple[str, int]:
        return self._normalize_side_key(side), int(turn_now)

    def _capture_budget_slot(self, side, turn_now: int) -> dict:
        key = self._capture_budget_key(side, turn_now)
        slot = self._capture_budget_by_side_turn.get(key)
        if slot is None:
            slot = {"required_advances": int(self._capture_budget_required_advances), "advance_count": 0, "decision_count": 0}
            self._capture_budget_by_side_turn[key] = slot
        return slot

    def _capture_budget_state_label(self, side, turn_now: int, budgeted_context: bool) -> str:
        if not budgeted_context:
            return "UNBOUNDED"
        slot = self._capture_budget_slot(side, turn_now)
        if int(slot.get("advance_count", 0)) < int(slot.get("required_advances", 0)):
            return "BUDGETED"
        return "EXHAUSTED"

    def _plan_intent_name(self, strategy: StrategicIntent | None) -> str:
        if strategy is None:
            return "UNKNOWN"
        return str(getattr(strategy, "name", "UNKNOWN") or "UNKNOWN").upper()

    def _plan_focus_vp_id(self, state, unit) -> str | None:
        if state is None or unit is None:
            return None
        target = self._objective_target_hex(state, unit)
        if target is None:
            return None
        return f"{target[0]},{target[1]}"

    def _locked_capture_focus_hex(self, state, unit):
        uid = getattr(unit, "unit_id", None)
        if not uid:
            return None
        slot = self._capture_focus_lock_by_unit.get(uid)
        if not slot:
            return None
        target = slot.get("target")
        ttl = int(slot.get("ttl", 0) or 0)
        if ttl <= 0 or target is None:
            self._capture_focus_lock_by_unit.pop(uid, None)
            return None
        if not self._is_uncaptured_vp_coords(state, getattr(unit, "side", None), target):
            self._capture_focus_lock_by_unit.pop(uid, None)
            return None
        return target

    def _set_capture_focus_lock(self, unit, target_hex, ttl: int | None = None):
        uid = getattr(unit, "unit_id", None)
        if not uid or target_hex is None:
            return
        lock_ttl = int(ttl if ttl is not None else self._capture_focus_ttl_steps)
        if lock_ttl <= 0:
            return
        self._capture_focus_lock_by_unit[uid] = {
            "target": (int(target_hex[0]), int(target_hex[1])),
            "ttl": lock_ttl,
        }

    def _tick_capture_focus_lock(self, unit):
        uid = getattr(unit, "unit_id", None)
        if not uid:
            return
        slot = self._capture_focus_lock_by_unit.get(uid)
        if not slot:
            return
        ttl = int(slot.get("ttl", 0) or 0) - 1
        if ttl <= 0:
            self._capture_focus_lock_by_unit.pop(uid, None)
            return
        slot["ttl"] = ttl

    def _plan_unit_role(self, state, unit, strategy: StrategicIntent | None) -> str:
        if unit is None:
            return "UNKNOWN"
        if state is None:
            if strategy == StrategicIntent.PRESERVE:
                return "RESERVE"
            if strategy == StrategicIntent.DENY:
                return "HOLD_VP"
            return "UNKNOWN"
        local_role = self._local_role_kind(state, unit)
        if local_role == "SUPPORT":
            return "SUPPORT_FIRE"
        if local_role == "ASSAULT":
            return "ASSAULT"
        if strategy == StrategicIntent.PRESERVE:
            return "RESERVE"
        if strategy == StrategicIntent.DENY:
            return "HOLD_VP"
        if strategy == StrategicIntent.CAPTURE:
            return "SCREEN"
        return "UNKNOWN"

    def _next_plan_step_id(self) -> int:
        self._plan_step_seq += 1
        return int(self._plan_step_seq)

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

    def _prepare_action_cache(self, state):
        state_key = id(state)
        if self._action_catalog_cache_state_key != state_key:
            self._action_catalog_cache_state_key = state_key
            self._action_catalog_cache = {}

    def _get_unit_actions(self, state, unit):
        if state is None or unit is None:
            return []
        uid = getattr(unit, "unit_id", None)
        if not uid:
            return ActionCatalog(state, unit, terrain_config).actions()
        cache_key = (self._action_catalog_cache_state_key, uid)
        cached = self._action_catalog_cache.get(cache_key)
        if cached is not None:
            return cached
        actions = ActionCatalog(state, unit, terrain_config).actions()
        self._action_catalog_cache[cache_key] = actions
        return actions

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
        locked = self._locked_capture_focus_hex(state, unit)
        if locked is not None:
            return locked
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

    def _is_target_near_uncaptured_vp(self, state, unit, target, max_dist: int = 1) -> bool:
        if target is None or getattr(target, "position", None) is None or unit is None:
            return False
        d = self._nearest_uncaptured_vp_dist_from_pos(state, unit.side, target.position)
        return d is not None and float(d) <= float(max_dist)

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
        actions = self._get_unit_actions(state, unit)
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

    def _is_uncaptured_vp_coords(self, state, side: str, coords) -> bool:
        if coords is None or not side:
            return False
        points = getattr(getattr(state, "victory", None), "points", []) or []
        if not points:
            return False
        vp_hexes = {vp.hex_coords for vp in points}
        key = (coords[0], coords[1])
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

    def _nearest_uncaptured_vp_ring_dist_from_pos(self, state, side: str, pos):
        d = self._nearest_uncaptured_vp_dist_from_pos(state, side, pos)
        if d is None:
            return None
        # Distance to the ring adjacent to an uncaptured VP hex.
        return max(0.0, float(d) - 1.0)

    def _enemy_pressure_at_pos(self, state, side: str, pos, radius: int = 3) -> float:
        if pos is None or not side:
            return 0.0
        pressure = 0.0
        for e in getattr(state, "units", []) or []:
            if not getattr(e, "alive", False):
                continue
            if getattr(e, "side", None) == side:
                continue
            epos = getattr(e, "position", None)
            if epos is None:
                continue
            d = safe_hex_distance(pos, epos)
            if d is None or d > radius:
                continue
            pressure += 1.0 / max(1.0, float(d))
        return float(pressure)

    def _best_capture_staging_move(self, state, unit):
        actions = self._get_unit_actions(state, unit)
        moves = [a for a in actions if getattr(getattr(a, "action_type", None), "category", None) == ActionCategory.MOVEMENT]
        if not moves:
            debug = {
                "move_candidates_total": 0,
                "progress_candidates": 0,
                "equal_candidates": 0,
                "increase_candidates": 0,
                "reversal_filtered": 0,
                "progress_available": False,
                "selected_reason": "no_movement_actions",
                "selected_dist_delta": None,
                "suspected_progress_miss": False,
            }
            return None, "no_movement_actions", None, None, debug

        dist_before = self._nearest_uncaptured_vp_dist(state, unit)
        ring_before = self._nearest_uncaptured_vp_ring_dist_from_pos(state, unit.side, unit.position)
        uid = getattr(unit, "unit_id", None)
        prev_pos = self._prev_pos_by_unit.get(uid) if uid else None
        best_any = None
        best_any_score = float("-inf")
        best_non_worse = None
        best_non_worse_score = float("-inf")
        best_progress = None
        best_progress_score = float("-inf")
        saw_equal = False
        saw_increase_only = True
        progress_candidates = 0
        equal_candidates = 0
        increase_candidates = 0
        reversal_filtered = 0
        legal_move_candidates = 0

        for m in moves:
            path = getattr(m, "path", None)
            if not path:
                continue
            end = path[-1]
            if self._is_reversal_move(unit, end) and not self._is_uncaptured_vp_hex(state, unit.side, end):
                # Hard stop to A->B->A oscillations during CAPTURE staging.
                reversal_filtered += 1
                continue
            dist_after = self._nearest_uncaptured_vp_dist_from_pos(state, unit.side, end)
            if dist_after is None:
                continue
            legal_move_candidates += 1
            ring_after = self._nearest_uncaptured_vp_ring_dist_from_pos(state, unit.side, end)
            enemy_pressure = self._enemy_pressure_at_pos(state, unit.side, end, radius=3)
            terrain_score = self._terrain_tactical_score(state, unit, end)
            score = -float(dist_after) + 0.3 * terrain_score - 0.35 * float(enemy_pressure)
            if ring_after is not None:
                score -= 0.8 * float(ring_after)
            if ring_before is not None and ring_after is not None:
                if float(ring_after) < float(ring_before):
                    score += 2.0
                elif float(ring_after) == float(ring_before):
                    score -= 0.6
            # Near VP, strongly discourage lateral equal-distance loops.
            if (
                dist_before is not None
                and float(dist_before) <= 3.0
                and float(dist_after) == float(dist_before)
            ):
                score -= 1.5
                end_t = (getattr(end, "q", None), getattr(end, "r", None))
                if prev_pos is not None and end_t == prev_pos:
                    score -= 1.5
            if self._is_reversal_move(unit, end):
                score -= 8.0
            if score > best_any_score:
                best_any_score = score
                best_any = (m, dist_after, score)
            if dist_before is not None and dist_after < dist_before:
                progress_candidates += 1
                saw_increase_only = False
                if score > best_progress_score:
                    best_progress_score = score
                    best_progress = (m, dist_after, score)
                if score > best_non_worse_score:
                    best_non_worse_score = score
                    best_non_worse = (m, dist_after, score)
            elif dist_before is not None and dist_after == dist_before:
                equal_candidates += 1
                saw_equal = True
                saw_increase_only = False
                # Allow lateral staging moves if not getting worse.
                if score > best_non_worse_score:
                    best_non_worse_score = score
                    best_non_worse = (m, dist_after, score)
            elif dist_before is not None and dist_after > dist_before:
                increase_candidates += 1

        def _build_debug(selected_reason: str, selected_after):
            dist_delta = None
            if dist_before is not None and selected_after is not None:
                dist_delta = float(dist_before) - float(selected_after)
            progress_available = progress_candidates > 0
            suspected_progress_miss = bool(progress_available and selected_reason != "objective_progress_move")
            return {
                "move_candidates_total": int(legal_move_candidates),
                "progress_candidates": int(progress_candidates),
                "equal_candidates": int(equal_candidates),
                "increase_candidates": int(increase_candidates),
                "reversal_filtered": int(reversal_filtered),
                "progress_available": bool(progress_available),
                "selected_reason": str(selected_reason or ""),
                "selected_dist_delta": dist_delta,
                "suspected_progress_miss": bool(suspected_progress_miss),
            }

        # Hard priority: when real VP progress exists, do not select lateral staging.
        if best_progress is not None:
            move, dist_after, _ = best_progress
            return move, "objective_progress_move", dist_before, dist_after, _build_debug("objective_progress_move", dist_after)

        if best_non_worse is not None:
            move, dist_after, _ = best_non_worse
            if dist_before is not None and dist_after < dist_before:
                return move, "objective_progress_move", dist_before, dist_after, _build_debug("objective_progress_move", dist_after)
            if dist_before is not None and dist_after == dist_before:
                return move, "objective_staging_move", dist_before, dist_after, _build_debug("objective_staging_move", dist_after)
            return move, "objective_staging_move", dist_before, dist_after, _build_debug("objective_staging_move", dist_after)
        if best_any is not None:
            move, dist_after, _ = best_any
            if saw_increase_only and dist_before is not None:
                return move, "all_moves_increase_distance", dist_before, dist_after, _build_debug("all_moves_increase_distance", dist_after)
            if saw_equal:
                return move, "only_equal_distance_moves", dist_before, dist_after, _build_debug("only_equal_distance_moves", dist_after)
            return move, "no_progress_move_available", dist_before, dist_after, _build_debug("no_progress_move_available", dist_after)
        return None, "no_movement_actions", dist_before, None, _build_debug("no_movement_actions", None)

    def _attach_capture_progress_debug(self, action, debug_snapshot):
        if action is None:
            return
        debug = debug_snapshot or {}
        action.rl_capture_move_candidates_total = int(debug.get("move_candidates_total", 0) or 0)
        action.rl_capture_progress_candidates = int(debug.get("progress_candidates", 0) or 0)
        action.rl_capture_equal_candidates = int(debug.get("equal_candidates", 0) or 0)
        action.rl_capture_increase_candidates = int(debug.get("increase_candidates", 0) or 0)
        action.rl_capture_reversal_filtered = int(debug.get("reversal_filtered", 0) or 0)
        action.rl_capture_progress_available = bool(debug.get("progress_available", False))
        action.rl_capture_selected_move_reason = str(debug.get("selected_reason", "") or "")
        action.rl_capture_selected_dist_delta = debug.get("selected_dist_delta", None)
        action.rl_capture_suspected_progress_miss = bool(debug.get("suspected_progress_miss", False))

    def _attach_vp_entry_debug(self, action, legal_stepin: bool, selected_stepin: bool, block_reason: str):
        if action is None:
            return
        action.rl_vp_stepin_legal = bool(legal_stepin)
        action.rl_vp_stepin_selected = bool(selected_stepin)
        action.rl_vp_stepin_block_reason = str(block_reason or "")
        if not hasattr(action, "rl_vp_nearest_uncaptured_dist"):
            action.rl_vp_nearest_uncaptured_dist = None
        if not hasattr(action, "rl_vp_opening_attack_candidates_count"):
            action.rl_vp_opening_attack_candidates_count = 0

    def _has_vp_attack_opportunity(self, state, unit) -> bool:
        if unit is None:
            return False
        actions = self._get_unit_actions(state, unit)
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
        self._capture_decision_seq += 1
        decision_seq = int(self._capture_decision_seq)
        step_into_vp_candidate = self._best_step_into_uncaptured_vp(state, unit)
        has_legal_stepin = step_into_vp_candidate is not None
        nearest_vp_d = self._nearest_uncaptured_vp_dist(state, unit)
        default_block_reason = ""
        if not has_legal_stepin:
            if nearest_vp_d is None or float(nearest_vp_d) >= 999.0:
                default_block_reason = "no_objective_reachable"
            elif float(nearest_vp_d) <= 2.0:
                default_block_reason = "no_legal_stepin_near_vp"
            else:
                default_block_reason = "no_legal_stepin"
        uid = getattr(unit, "unit_id", None)
        if uid:
            if default_block_reason == "no_legal_stepin_near_vp":
                self._capture_no_stepin_near_streak_by_unit[uid] = int(self._capture_no_stepin_near_streak_by_unit.get(uid, 0)) + 1
            else:
                self._capture_no_stepin_near_streak_by_unit[uid] = 0
        open_window_throttle_ok = True
        if uid:
            last_seq = int(self._capture_open_window_last_seq_by_unit.get(uid, -999999))
            open_window_throttle_ok = (decision_seq - last_seq) >= 2

        # 1) Emergency handling: allow retreat.
        if self._is_capture_emergency(state, unit):
            action = self.heuristic.choose_action(state, unit, TacticalOption.RETREAT)
            if isinstance(action, (RangedDirectAttack, RangedIndirectAttack)):
                action = WaitAction(unit.unit_id)
            if action is not None:
                action.rl_capture_fallback_reason = "capture_emergency"
                action.rl_capture_move_block_profile = "emergency_blocked"
                self._attach_vp_entry_debug(action, has_legal_stepin, False, "capture_emergency")
            return action or WaitAction(unit.unit_id), TacticalOption.RETREAT

        # 2) If we can occupy an uncaptured VP now, do it immediately.
        step_into_vp = step_into_vp_candidate
        if step_into_vp is not None:
            d_before = self._nearest_uncaptured_vp_dist(state, unit)
            step_into_vp.rl_capture_fallback_reason = "step_into_uncaptured_vp"
            step_into_vp.rl_capture_move_block_profile = "step_into_uncaptured_vp"
            step_into_vp.rl_capture_target_dist_before = d_before
            step_into_vp.rl_capture_target_dist_after = 0
            self._attach_vp_entry_debug(step_into_vp, True, True, "")
            return step_into_vp, TacticalOption.ADVANCE

        # 3) Evaluate movement and attacks jointly near VP.
        move, move_reason, dist_before, dist_after, move_debug = self._best_capture_staging_move(state, unit)
        if not move_reason:
            move_reason = "no_movement_actions"
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
                    self._attach_capture_progress_debug(forced, move_debug)
                    return forced, TacticalOption.ATTACK
        if attacks:
            vp_relevant_attacks = []
            vp_opening_attacks = []
            for a in attacks:
                target = self._resolve_action_target(state, a)
                if target is None or not getattr(target, "alive", False):
                    continue
                target_on_vp = self._is_target_on_enemy_or_neutral_vp(state, unit, target)
                target_on_owned_vp = self._is_target_on_owned_vp(state, unit, target)
                target_near_uncaptured_vp = self._is_target_near_uncaptured_vp(state, unit, target, max_dist=1)
                if target_on_vp or target_on_owned_vp:
                    vp_relevant_attacks.append(a)
                if target_on_vp or target_on_owned_vp or target_near_uncaptured_vp:
                    vp_opening_attacks.append(a)
            # VP-window opening guardrail:
            # near uncaptured objectives, if no immediate step-in is possible,
            # force a VP-relevant attack to open a capture lane.
            if (
                nearest_vp_d is not None
                and float(nearest_vp_d) <= 3.0
                and (
                    move_reason in {"objective_staging_move", "all_moves_increase_distance", "no_progress_move_available"}
                    or (
                        default_block_reason == "no_legal_stepin_near_vp"
                        and int(self._capture_no_stepin_near_streak_by_unit.get(uid, 0) if uid else 0) >= 1
                    )
                )
                and vp_opening_attacks
                and open_window_throttle_ok
            ):
                open_window = self._best_attack(vp_opening_attacks, state=state, unit=unit)
                if open_window is not None:
                    open_window.rl_capture_fallback_to_attack = True
                    open_window.rl_capture_fallback_reason = "forced_attack_open_vp_window"
                    open_window.rl_capture_move_block_profile = move_reason or "no_progress_move_available"
                    open_window.rl_capture_target_dist_before = dist_before
                    open_window.rl_capture_target_dist_after = dist_after
                    open_window.rl_vp_opening_attack_candidates_count = int(len(vp_opening_attacks))
                    self._attach_capture_progress_debug(open_window, move_debug)
                    self._attach_vp_entry_debug(open_window, has_legal_stepin, False, default_block_reason or move_reason or "forced_attack_open_vp_window")
                    open_window.rl_vp_nearest_uncaptured_dist = nearest_vp_d
                    if uid:
                        self._capture_open_window_last_seq_by_unit[uid] = decision_seq
                    return open_window, TacticalOption.ATTACK
            # Near-VP strict capture conversion:
            # avoid non-VP attack/hold drift when no legal step-in exists.
            # If close to VP, movement progression has priority unless
            # lane-opening attack fallback was chosen above.
            if nearest_vp_d is not None and float(nearest_vp_d) <= 2.0:
                if move is not None and move_reason in {"objective_progress_move", "objective_staging_move"}:
                    move.rl_capture_fallback_reason = move_reason
                    move.rl_capture_move_block_profile = move_reason
                    move.rl_capture_target_dist_before = dist_before
                    move.rl_capture_target_dist_after = dist_after
                    move.rl_vp_opening_attack_candidates_count = int(len(vp_opening_attacks))
                    self._attach_capture_progress_debug(move, move_debug)
                    self._attach_vp_entry_debug(move, has_legal_stepin, False, default_block_reason or move_reason)
                    move.rl_vp_nearest_uncaptured_dist = nearest_vp_d
                    return move, TacticalOption.ADVANCE
            # Hard anti-lateralization near VP:
            # if CAPTURE is still selecting staging while already close to an
            # uncaptured objective, force an attack to break local loops.
            if (
                move_reason == "objective_staging_move"
                and nearest_vp_d is not None
                and float(nearest_vp_d) <= 2.0
            ):
                forced_near_vp_pool = vp_relevant_attacks if vp_relevant_attacks else attacks
                forced_near_vp = self._best_attack(forced_near_vp_pool, state=state, unit=unit)
                if forced_near_vp is not None:
                    forced_near_vp.rl_capture_fallback_to_attack = True
                    forced_near_vp.rl_capture_fallback_reason = "forced_attack_near_vp_staging"
                    forced_near_vp.rl_capture_move_block_profile = move_reason or "objective_staging_move"
                    forced_near_vp.rl_capture_target_dist_before = dist_before
                    forced_near_vp.rl_capture_target_dist_after = dist_after
                    forced_near_vp.rl_vp_opening_attack_candidates_count = int(len(vp_opening_attacks))
                    self._attach_capture_progress_debug(forced_near_vp, move_debug)
                    self._attach_vp_entry_debug(forced_near_vp, has_legal_stepin, False, default_block_reason or move_reason or "forced_attack_near_vp_staging")
                    forced_near_vp.rl_vp_nearest_uncaptured_dist = nearest_vp_d
                    return forced_near_vp, TacticalOption.ATTACK
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
                    gated.rl_capture_move_block_profile = move_reason or "no_progress_move_available"
                    gated.rl_capture_target_dist_before = dist_before
                    gated.rl_capture_target_dist_after = dist_after
                    gated.rl_vp_opening_attack_candidates_count = int(len(vp_opening_attacks))
                    self._attach_capture_progress_debug(gated, move_debug)
                    self._attach_vp_entry_debug(gated, has_legal_stepin, False, default_block_reason or move_reason or gated_reason)
                    gated.rl_vp_nearest_uncaptured_dist = nearest_vp_d
                    return gated, TacticalOption.ATTACK

        # 5) Prefer movement if it does not worsen VP progress.
        if move is not None and move_reason in {"objective_progress_move", "objective_staging_move"}:
            move.rl_capture_fallback_reason = move_reason
            move.rl_capture_move_block_profile = move_reason
            move.rl_capture_target_dist_before = dist_before
            move.rl_capture_target_dist_after = dist_after
            self._attach_capture_progress_debug(move, move_debug)
            self._attach_vp_entry_debug(move, has_legal_stepin, False, default_block_reason or move_reason)
            move.rl_vp_nearest_uncaptured_dist = nearest_vp_d
            move.rl_vp_opening_attack_candidates_count = 0
            return move, TacticalOption.ADVANCE

        # 6) If attacks are gated and movement is poor, still allow attack fallback.
        if attacks:
            # CAPTURE relaxed fallback should stay VP-relevant to avoid
            # drifting into attrition loops near objectives.
            relaxed_pool = []
            for a in attacks:
                target = self._resolve_action_target(state, a)
                if target is None or not getattr(target, "alive", False):
                    continue
                if (
                    self._is_target_on_enemy_or_neutral_vp(state, unit, target)
                    or self._is_target_on_owned_vp(state, unit, target)
                ):
                    relaxed_pool.append(a)
            best = self._best_attack(relaxed_pool, state=state, unit=unit) if relaxed_pool else None
            if best is not None:
                best.rl_capture_fallback_to_attack = True
                best.rl_capture_fallback_reason = "attack_gate_relaxed_fallback"
                best.rl_capture_move_block_profile = move_reason or "no_progress_move_available"
                best.rl_capture_target_dist_before = dist_before
                best.rl_capture_target_dist_after = dist_after
                self._attach_capture_progress_debug(best, move_debug)
                self._attach_vp_entry_debug(best, has_legal_stepin, False, default_block_reason or move_reason or "attack_gate_relaxed_fallback")
                best.rl_vp_nearest_uncaptured_dist = nearest_vp_d
                best.rl_vp_opening_attack_candidates_count = int(len(relaxed_pool))
                return best, TacticalOption.ATTACK

        # 7) Fallback movement / hold.
        if move is not None:
            move.rl_capture_fallback_reason = "fallback_move_even_if_no_progress"
            move.rl_capture_move_block_profile = move_reason
            move.rl_capture_target_dist_before = dist_before
            move.rl_capture_target_dist_after = dist_after
            self._attach_capture_progress_debug(move, move_debug)
            self._attach_vp_entry_debug(move, has_legal_stepin, False, default_block_reason or move_reason or "fallback_move_even_if_no_progress")
            move.rl_vp_nearest_uncaptured_dist = nearest_vp_d
            move.rl_vp_opening_attack_candidates_count = 0
            return move, TacticalOption.ADVANCE
        hold = WaitAction(unit.unit_id)
        hold.rl_capture_fallback_reason = "no_move_no_attack_hold"
        hold.rl_capture_move_block_profile = move_reason or "no_movement_actions"
        self._attach_capture_progress_debug(hold, move_debug)
        self._attach_vp_entry_debug(hold, has_legal_stepin, False, default_block_reason or move_reason or "no_move_no_attack_hold")
        hold.rl_vp_nearest_uncaptured_dist = nearest_vp_d
        hold.rl_vp_opening_attack_candidates_count = 0
        return hold, TacticalOption.HOLD

    def _tag_action(
        self,
        action,
        option: TacticalOption,
        strategy: StrategicIntent | None,
        state=None,
        unit=None,
        budget_state: str = "UNBOUNDED",
        emergency_override: bool = False,
        legal_override: bool = False,
        override_reason: str = "",
    ):
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
        if not hasattr(action, "rl_capture_move_candidates_total"):
            action.rl_capture_move_candidates_total = 0
        if not hasattr(action, "rl_capture_progress_candidates"):
            action.rl_capture_progress_candidates = 0
        if not hasattr(action, "rl_capture_equal_candidates"):
            action.rl_capture_equal_candidates = 0
        if not hasattr(action, "rl_capture_increase_candidates"):
            action.rl_capture_increase_candidates = 0
        if not hasattr(action, "rl_capture_reversal_filtered"):
            action.rl_capture_reversal_filtered = 0
        if not hasattr(action, "rl_capture_progress_available"):
            action.rl_capture_progress_available = False
        if not hasattr(action, "rl_capture_selected_move_reason"):
            action.rl_capture_selected_move_reason = ""
        if not hasattr(action, "rl_capture_selected_dist_delta"):
            action.rl_capture_selected_dist_delta = None
        if not hasattr(action, "rl_capture_suspected_progress_miss"):
            action.rl_capture_suspected_progress_miss = False
        if not hasattr(action, "rl_vp_stepin_legal"):
            action.rl_vp_stepin_legal = False
        if not hasattr(action, "rl_vp_stepin_selected"):
            action.rl_vp_stepin_selected = False
        if not hasattr(action, "rl_vp_stepin_block_reason"):
            action.rl_vp_stepin_block_reason = ""
        if not hasattr(action, "rl_vp_nearest_uncaptured_dist"):
            action.rl_vp_nearest_uncaptured_dist = None
        if not hasattr(action, "rl_vp_opening_attack_candidates_count"):
            action.rl_vp_opening_attack_candidates_count = 0
        prev_emergency = bool(getattr(action, "rl_capture_emergency_override", False))
        prev_legal = bool(getattr(action, "rl_capture_legal_override", False))
        prev_reason = str(getattr(action, "rl_capture_override_reason", "") or "")
        action.rl_capture_emergency_override = bool(prev_emergency or emergency_override)
        action.rl_capture_legal_override = bool(prev_legal or legal_override)
        if override_reason:
            action.rl_capture_override_reason = str(override_reason)
        else:
            action.rl_capture_override_reason = prev_reason
        plan_unit = unit
        if plan_unit is None and getattr(action, "unit_id", None) and state is not None:
            uid = getattr(action, "unit_id", None)
            plan_unit = next((u for u in getattr(state, "units", []) if getattr(u, "unit_id", None) == uid), None)
        action.rl_plan_intent = self._plan_intent_name(strategy)
        action.rl_plan_unit_role = self._plan_unit_role(state, plan_unit, strategy)
        action.rl_plan_focus_vp_id = self._plan_focus_vp_id(state, plan_unit)
        action.rl_plan_step_id = self._next_plan_step_id()
        action.rl_plan_budget_state = str(budget_state or "UNBOUNDED")
        action.rl_plan_progress_stub = 0.0
        action.rl_plan_intent_alignment_stub = 0.0
        # Keep short-lived target commitment during CAPTURE to reduce target ping-pong.
        if strategy == StrategicIntent.CAPTURE and unit is not None:
            focus_hex = self._objective_target_hex(state, unit)
            if focus_hex is not None:
                before = getattr(action, "rl_capture_target_dist_before", None)
                after = getattr(action, "rl_capture_target_dist_after", None)
                made_progress = (
                    isinstance(before, (int, float))
                    and isinstance(after, (int, float))
                    and float(after) < float(before)
                )
                ttl = self._capture_focus_ttl_steps + (1 if made_progress else 0)
                self._set_capture_focus_lock(unit, focus_hex, ttl=ttl)
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
        self._tick_capture_focus_lock(unit)
        self._update_position_history(unit)
        self._prepare_action_cache(state)
        tracked_side_norm = self._normalize_side_key(objective_tracked_side)
        unit_side_norm = self._normalize_side_key(getattr(unit, "side", None))
        attacker_context = bool(tracked_side_norm) and unit_side_norm == tracked_side_norm
        defender_context = bool(tracked_side_norm) and unit_side_norm != tracked_side_norm
        objectives_pending = self._has_uncaptured_objective_for_side(state, unit.side)
        capture_emergency = self._is_capture_emergency(state, unit)
        aggressive_l3_forced = False
        if (
            self.diagnostic_force_capture_only
            and not capture_emergency
            and (not tracked_side_norm or attacker_context)
        ):
            strategy = StrategicIntent.CAPTURE
            aggressive_l3_forced = True
        if (
            objectives_pending
            and not capture_emergency
            and (not tracked_side_norm or attacker_context)
            and strategy != StrategicIntent.CAPTURE
        ):
            strategy = StrategicIntent.CAPTURE
            aggressive_l3_forced = True

        if not self.capture_guardrails_enabled:
            option = self._resolve_option_for_strategy(state, unit, option, strategy)
            option = self._apply_local_role_bias(state, unit, option, strategy)

            def _tag_no_guard(action_to_tag, chosen_option: TacticalOption):
                return self._tag_action(
                    action_to_tag,
                    chosen_option,
                    strategy,
                    state=state,
                    unit=unit,
                    budget_state="UNBOUNDED",
                    emergency_override=bool(capture_emergency),
                    legal_override=bool(aggressive_l3_forced),
                    override_reason=("aggressive_l3_capture_force" if aggressive_l3_forced else ""),
                )

            if option == TacticalOption.ATTACK:
                return _tag_no_guard(self._execute_attack(state, unit, attack_mode), option)
            if option == TacticalOption.ADVANCE:
                return _tag_no_guard(self._move_closer(state, unit, capture_strict=False), option)
            if option == TacticalOption.FLANK:
                return _tag_no_guard(self._flank_move(state, unit), option)
            if option == TacticalOption.RETREAT:
                action = self.heuristic.choose_action(state, unit, option)
                if isinstance(action, (RangedDirectAttack, RangedIndirectAttack)):
                    return _tag_no_guard(WaitAction(unit.unit_id), option)
                return _tag_no_guard(action or WaitAction(unit.unit_id), option)
            if option == TacticalOption.HOLD:
                actions = self._get_unit_actions(state, unit)
                attacks = [a for a in actions if self._is_attack_action(a)]
                if attacks:
                    best = self._best_attack(attacks, state=state, unit=unit)
                    return _tag_no_guard(best if best else attacks[0], option)
                return _tag_no_guard(WaitAction(unit.unit_id), option)
            return _tag_no_guard(WaitAction(unit.unit_id), option)

        # Mission guardrail: when objectives are still pending, avoid being stuck
        # in PRESERVE unless this unit is in a genuine emergency.
        if (
            strategy == StrategicIntent.PRESERVE
            and objectives_pending
            and not capture_emergency
            and (not tracked_side_norm or attacker_context)
        ):
            strategy = StrategicIntent.CAPTURE
        # If we're behind on objectives, force CAPTURE intent (unless emergency).
        if (
            strategy in (StrategicIntent.PRESERVE, StrategicIntent.ATTRIT, StrategicIntent.DENY)
            and objectives_pending
            and self._is_behind_on_objectives(state, unit.side)
            and not capture_emergency
            and (not tracked_side_norm or attacker_context)
        ):
            strategy = StrategicIntent.CAPTURE
        # If objectives are still pending, avoid over-defensive DENY loops and
        # push capture intent unless this unit is in a genuine emergency.
        if (
            strategy == StrategicIntent.DENY
            and objectives_pending
            and not capture_emergency
            and (not tracked_side_norm or attacker_context)
        ):
            strategy = StrategicIntent.CAPTURE
        # Scenario role guardrail:
        # if this side is the defender (not tracked in objective table),
        # avoid CAPTURE loops and bias to DENY.
        if defender_context and strategy == StrategicIntent.CAPTURE:
            strategy = StrategicIntent.DENY

        # Deterministic CAPTURE controller to avoid reward-driven local loops.
        # Hard gate: in CAPTURE, if a VP entry is immediately available, force it.
        if (
            strategy == StrategicIntent.CAPTURE
            and objectives_pending
            and not capture_emergency
        ):
            step_into_vp = self._best_step_into_uncaptured_vp(state, unit)
            if step_into_vp is not None:
                d_before = self._nearest_uncaptured_vp_dist(state, unit)
                step_into_vp.rl_capture_fallback_reason = "hard_gate_step_into_uncaptured_vp"
                step_into_vp.rl_capture_move_block_profile = "hard_gate_step_into_uncaptured_vp"
                step_into_vp.rl_capture_target_dist_before = d_before
                step_into_vp.rl_capture_target_dist_after = 0
                self._attach_vp_entry_debug(step_into_vp, True, True, "")
                return self._tag_action(
                    step_into_vp,
                    TacticalOption.ADVANCE,
                    strategy,
                    state=state,
                    unit=unit,
                    legal_override=True,
                    override_reason="hard_gate_step_into_uncaptured_vp",
                )

        if (
            strategy == StrategicIntent.CAPTURE
            and objectives_pending
        ):
            action, chosen_option = self._capture_priority_action(state, unit, attack_mode)
            return self._tag_action(action, chosen_option, strategy, state=state, unit=unit)

        option = self._resolve_option_for_strategy(state, unit, option, strategy)
        option = self._apply_local_role_bias(state, unit, option, strategy)
        turn_now = int(getattr(state, "turn", 0))
        nearest_vp_d = self._nearest_uncaptured_vp_dist(state, unit)
        budgeted_context = (
            objectives_pending
            and not capture_emergency
            and (not tracked_side_norm or attacker_context)
            and nearest_vp_d is not None
            and nearest_vp_d <= 3
        )

        legal_override_applied = False
        emergency_override_applied = bool(capture_emergency)
        override_reason = ""

        def _tag_with_budget(action_to_tag, chosen_option: TacticalOption):
            budget_state = "UNBOUNDED"
            if budgeted_context:
                slot = self._capture_budget_slot(unit.side, turn_now)
                slot["decision_count"] = int(slot.get("decision_count", 0)) + 1
                if chosen_option == TacticalOption.ADVANCE:
                    slot["advance_count"] = int(slot.get("advance_count", 0)) + 1
                budget_state = self._capture_budget_state_label(unit.side, turn_now, True)
            return self._tag_action(
                action_to_tag,
                chosen_option,
                strategy,
                state=state,
                unit=unit,
                budget_state=budget_state,
                emergency_override=emergency_override_applied,
                legal_override=legal_override_applied,
                override_reason=override_reason,
            )

        if (
            self._has_uncaptured_objective(state, unit)
            and not capture_emergency
        ):
            # Hard priority: if a VP can be occupied now, do it before shooting.
            step_into_vp = self._best_step_into_uncaptured_vp(state, unit)
            if step_into_vp is not None:
                return _tag_with_budget(step_into_vp, TacticalOption.ADVANCE)
        # Hard temporal capture curriculum:
        # while objectives are pending, early episode/turn CAPTURE should advance
        # toward VP unless there is an emergency or a high-value VP attack.
        if (
            strategy == StrategicIntent.CAPTURE
            and self._has_uncaptured_objective(state, unit)
            and not capture_emergency
            and turn_now <= 8
            and not self._has_vp_attack_opportunity(state, unit)
        ):
            if option != TacticalOption.ADVANCE:
                legal_override_applied = True
                override_reason = "capture_early_turn_priority"
            option = TacticalOption.ADVANCE
        # P4.3b soft budget:
        # near VP and with pending objectives, avoid drifting to ATTACK/HOLD unless
        # the attack is directly VP-relevant or there is an emergency.
        if (
            objectives_pending
            and not capture_emergency
            and nearest_vp_d is not None
            and nearest_vp_d <= 3
            and option in (TacticalOption.ATTACK, TacticalOption.HOLD)
            and not self._has_vp_attack_opportunity(state, unit)
        ):
            legal_override_applied = True
            override_reason = "soft_budget_entry_first"
            option = TacticalOption.ADVANCE
        # P4.3c hard budget (light):
        # near VP, demand a minimum number of ADVANCE decisions per side/turn
        # unless there is an emergency or a VP-relevant attack.
        if budgeted_context:
            slot = self._capture_budget_slot(unit.side, turn_now)
            need_advances = int(slot.get("advance_count", 0)) < int(slot.get("required_advances", 0))
            if (
                need_advances
                and option in (TacticalOption.ATTACK, TacticalOption.HOLD, TacticalOption.RETREAT)
                and not self._has_vp_attack_opportunity(state, unit)
            ):
                legal_override_applied = True
                override_reason = "hard_budget_min_advances"
                option = TacticalOption.ADVANCE
        if (
            strategy in (StrategicIntent.CAPTURE, StrategicIntent.DENY)
            and option == TacticalOption.RETREAT
            and self._has_uncaptured_objective(state, unit)
            and not capture_emergency
        ):
            legal_override_applied = True
            override_reason = "retreat_blocked_pending_objectives"
            option = TacticalOption.ADVANCE
        if (
            strategy == StrategicIntent.PRESERVE
            and option in (TacticalOption.RETREAT, TacticalOption.HOLD, TacticalOption.ADVANCE)
            and not capture_emergency
            and self._has_immediate_attack(state, unit)
            and not budgeted_context
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
            legal_override_applied = True
            override_reason = "retreat_streak_blocked"
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
                # If close to VP and trying to camp-attack, force movement toward capture.
                if nearest_vp_d is not None and nearest_vp_d <= 2:
                    return _tag_with_budget(self._move_closer(state, unit, capture_strict=True), TacticalOption.ADVANCE)
            return _tag_with_budget(self._execute_attack(state, unit, attack_mode), option)

        # -------------------------------------------------
        if option == TacticalOption.ADVANCE:
            return _tag_with_budget(
                self._move_closer(state, unit, capture_strict=(strategy == StrategicIntent.CAPTURE)),
                option,
            )

        # -------------------------------------------------
        if option == TacticalOption.FLANK:
            return _tag_with_budget(self._flank_move(state, unit), option)

        # -------------------------------------------------
        # ✅ RETREAT (NO ATAQUE)
        # -------------------------------------------------
        if option == TacticalOption.RETREAT:

            action = self.heuristic.choose_action(state, unit, option)

            if isinstance(action, (RangedDirectAttack, RangedIndirectAttack)):
                return _tag_with_budget(WaitAction(unit.unit_id), option)

            return _tag_with_budget(action or WaitAction(unit.unit_id), option)

        # -------------------------------------------------
        # ✅ HOLD (MEJORADO CON FALLBACK)
        # -------------------------------------------------
        if option == TacticalOption.HOLD:

            actions = self._get_unit_actions(state, unit)

            attacks = [
                a for a in actions
                if self._is_attack_action(a)
            ]

            if attacks:
                best = self._best_attack(attacks, state=state, unit=unit)
                return _tag_with_budget(best if best else attacks[0], option)
            # If there are relevant objectives to capture, avoid pure passivity.
            if self._objective_target_hex(state, unit) is not None:
                return _tag_with_budget(self._move_closer(state, unit), option)
            return _tag_with_budget(WaitAction(unit.unit_id), option)

        return _tag_with_budget(WaitAction(unit.unit_id), option)

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

        actions = self._get_unit_actions(state, unit)

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
        actions = self._get_unit_actions(state, unit)
        return any(self._is_attack_action(a) for a in actions)

    # -------------------------------------------------
    def _move_closer(self, state, unit, capture_strict: bool = False):

        actions = self._get_unit_actions(state, unit)

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
        best_non_worse = None
        best_non_worse_score = float("-inf")
        dist_before_target = None
        if objective_target is not None and getattr(unit, "position", None) is not None:
            dist_before_target = safe_hex_distance(unit.position, objective_target)

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
            if capture_strict:
                # CAPTURE strict mode: prioritize objective distance over terrain comfort.
                score = -100.0 * float(d) + 0.1 * _MOVE_CFG.advance_terrain_weight * terrain_score
            else:
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
            if (
                capture_strict
                and dist_before_target is not None
                and d <= dist_before_target
                and score > best_non_worse_score
            ):
                best_non_worse = a
                best_non_worse_score = score

        if capture_strict and best_non_worse is not None:
            return best_non_worse
        return best or WaitAction(unit.unit_id)

    # -------------------------------------------------
    def _flank_move(self, state, unit):

        actions = self._get_unit_actions(state, unit)

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
