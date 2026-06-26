from assault_model.actions.action_catalog import ActionCatalog
from assault_model.actions.action_category import ActionCategory
from assault_model.map.hex_utils import safe_hex_distance
from assault_model.map.terrain_config import terrain_config
import numpy as np


class OptionExecutorStateMixin:
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

    def _capture_budget_key(self, side, turn_now: int) -> tuple[str, int]:
        return self._normalize_side_key(side), int(turn_now)

    def _capture_budget_slot(self, side, turn_now: int) -> dict:
        key = self._capture_budget_key(side, turn_now)
        slot = self._capture_budget_by_side_turn.get(key)
        if slot is None:
            slot = {
                "required_advances": int(self._capture_budget_required_advances),
                "advance_count": 0,
                "decision_count": 0,
                "violation_count": 0,
            }
            self._capture_budget_by_side_turn[key] = slot
        return slot

    def _capture_budget_state_label(self, side, turn_now: int, budgeted_context: bool) -> str:
        if not budgeted_context:
            return "UNBOUNDED"
        slot = self._capture_budget_slot(side, turn_now)
        if int(slot.get("advance_count", 0)) < int(slot.get("required_advances", 0)):
            return "BUDGETED"
        return "EXHAUSTED"

    def _l3_capture_quota_slot(self, side, turn_now: int) -> dict:
        key = self._capture_budget_key(side, turn_now)
        slot = self._l3_capture_quota_by_side_turn.get(key)
        if slot is None:
            slot = {"required_capture": int(self._l3_capture_quota_required), "capture_count": 0, "decision_count": 0}
            self._l3_capture_quota_by_side_turn[key] = slot
        return slot

    def _plan_intent_name(self, strategy) -> str:
        if strategy is None:
            return "UNKNOWN"
        return str(getattr(strategy, "name", "UNKNOWN") or "UNKNOWN").upper()

    def _plan_intent_alignment_label(self, plan_intent: str) -> str:
        intent = str(plan_intent or "").upper().strip()
        if not intent:
            return "UNKNOWN"
        if intent == "SETUP_CAPTURE":
            return "CAPTURE"
        return intent

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
        state_key = (id(state), int(getattr(state, "_cache_version", 0)))
        if self._action_catalog_cache_state_key != state_key:
            self._action_catalog_cache_state_key = state_key
            self._action_catalog_cache = {}
            self._geom_cache = {}
            self._stepin_next_cache = {}
            self._target_cache = {}
            self._terrain_score_cache = {}

    def _enemy_positions_array(self, state, side: str):
        if state is None or not side:
            return np.empty((0, 2), dtype=np.int16)
        key = ("enemy_pos", self._action_catalog_cache_state_key, self._normalize_side_key(side))
        cached = self._geom_cache.get(key)
        if cached is not None:
            return cached
        rows = []
        for u in getattr(state, "units", []) or []:
            if not getattr(u, "alive", False):
                continue
            if self._normalize_side_key(getattr(u, "side", None)) == self._normalize_side_key(side):
                continue
            pos = getattr(u, "position", None)
            if pos is None:
                continue
            rows.append((int(pos.q), int(pos.r)))
        arr = np.asarray(rows, dtype=np.int16) if rows else np.empty((0, 2), dtype=np.int16)
        self._geom_cache[key] = arr
        return arr

    def _uncaptured_vp_coords_array(self, state, side: str):
        if state is None or not side:
            return np.empty((0, 2), dtype=np.int16)
        key = ("uncaptured_vp", self._action_catalog_cache_state_key, self._normalize_side_key(side))
        cached = self._geom_cache.get(key)
        if cached is not None:
            return cached
        points = getattr(getattr(state, "victory", None), "points", []) or []
        own_ownership = self._ownership_for_side(state, side)
        rows = []
        for vp in points:
            hs = state.hex_states.get(vp.hex_coords)
            if hs is not None and hs.ownership == own_ownership:
                continue
            rows.append((int(vp.hex_coords[0]), int(vp.hex_coords[1])))
        arr = np.asarray(rows, dtype=np.int16) if rows else np.empty((0, 2), dtype=np.int16)
        self._geom_cache[key] = arr
        return arr

    def _min_hex_distance_to_coords(self, pos, coords: np.ndarray):
        if pos is None or coords is None or int(getattr(coords, "size", 0)) == 0:
            return None
        q0 = int(getattr(pos, "q", 0))
        r0 = int(getattr(pos, "r", 0))
        dq = np.abs(coords[:, 0].astype(np.int32) - q0)
        dr = np.abs(coords[:, 1].astype(np.int32) - r0)
        ds = np.abs((coords[:, 0].astype(np.int32) + coords[:, 1].astype(np.int32)) - (q0 + r0))
        return int(np.min(np.maximum(np.maximum(dq, dr), ds)))

    def _unit_actions_cache_key(self, state, unit):
        if state is None or unit is None:
            return None
        uid = getattr(unit, "unit_id", None)
        if not uid:
            return None
        pos = getattr(unit, "position", None)
        return (
            self._action_catalog_cache_state_key,
            uid,
            getattr(pos, "q", None),
            getattr(pos, "r", None),
            bool(getattr(unit, "alive", True)),
            bool(getattr(unit, "can_fire", True)),
            bool(getattr(unit, "suppressed", False)),
            bool(getattr(unit, "fallback", False)),
            tuple(sorted(getattr(unit, "spotted_enemies", []) or [])),
        )

    def _get_unit_actions(self, state, unit):
        if state is None or unit is None:
            return []
        cache_key = self._unit_actions_cache_key(state, unit)
        if cache_key is None:
            return ActionCatalog(state, unit, terrain_config).actions()
        cached = self._action_catalog_cache.get(cache_key)
        if cached is not None:
            return cached
        actions = ActionCatalog(state, unit, terrain_config).actions()
        self._action_catalog_cache[cache_key] = actions
        return actions

    def _get_unit_actions_partitioned(self, state, unit):
        actions = self._get_unit_actions(state, unit)
        cache_key = self._unit_actions_cache_key(state, unit)
        if cache_key is None:
            moves = []
            attacks = []
            for a in actions:
                if getattr(getattr(a, "action_type", None), "category", None) == ActionCategory.MOVEMENT:
                    moves.append(a)
                if self._is_attack_action(a):  # type: ignore[attr-defined]
                    attacks.append(a)
            return actions, moves, attacks
        part_key = ("partitioned", cache_key)
        cached = self._action_catalog_cache.get(part_key)
        if cached is not None:
            return cached
        moves = []
        attacks = []
        for a in actions:
            if getattr(getattr(a, "action_type", None), "category", None) == ActionCategory.MOVEMENT:
                moves.append(a)
            if self._is_attack_action(a):  # type: ignore[attr-defined]
                attacks.append(a)
        out = (actions, moves, attacks)
        self._action_catalog_cache[part_key] = out
        return out

    def _is_reversal_move(self, unit, new_pos) -> bool:
        uid = getattr(unit, "unit_id", None)
        if not uid or new_pos is None:
            return False
        prevprev = self._prevprev_pos_by_unit.get(uid)
        if prevprev is None:
            return False
        return (new_pos.q, new_pos.r) == prevprev

    def _normalize_side_key(self, side) -> str:
        return str(getattr(side, "value", side) or "").upper()

    def _ownership_for_side(self, state, side):
        side_to_ownership = getattr(state, "side_to_ownership", {}) or {}
        key = self._normalize_side_key(side)
        if not key:
            return None
        own = side_to_ownership.get(key)
        if own is not None:
            return own
        for k, v in side_to_ownership.items():
            if self._normalize_side_key(k) == key:
                return v
        return None

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
        if pos is None or unit is None:
            return 0.0
        q = getattr(pos, "q", None)
        r = getattr(pos, "r", None)
        if q is None or r is None:
            return 0.0
        group = self._unit_group(unit)
        key = ("terrain_score", self._action_catalog_cache_state_key, int(q), int(r), str(group))
        cached = self._terrain_score_cache.get(key)
        if cached is not None:
            return float(cached)
        terrain_name = self._hex_terrain_name(state, pos)
        defense_score = float(len(terrain_config.get_defense_dice(terrain_name, group)))
        los = str(terrain_config.get_los(terrain_name)).upper()
        los_bonus = 0.0
        if los == "HINDERED":
            los_bonus = 0.35
        elif los == "BLOCKED":
            los_bonus = 0.6
        score = float(defense_score + los_bonus)
        self._terrain_score_cache[key] = score
        return score

    def _nearest_uncaptured_vp_dist_from_pos(self, state, side: str, pos):
        if pos is None or not side:
            return None
        vp_coords = self._uncaptured_vp_coords_array(state, side)
        d = self._min_hex_distance_to_coords(pos, vp_coords)
        if d is not None:
            return d
        points = getattr(getattr(state, "victory", None), "points", []) or []
        if not points:
            return None
        own_ownership = self._ownership_for_side(state, side)
        best = None
        for vp in points:
            hs = state.hex_states.get(vp.hex_coords)
            if hs is not None and hs.ownership == own_ownership:
                continue
            dist = safe_hex_distance(pos, vp.hex_coords)
            if best is None or dist < best:
                best = dist
        return best


__all__ = ["OptionExecutorStateMixin"]
