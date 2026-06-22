from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

from assault_model.actions.action_catalog import ActionCatalog
from assault_model.map.hex_utils import safe_hex_distance


@dataclass
class PlannerContext:
    side: str
    unit_id: str
    intent: str
    stage: str
    focus_vp_id: str | None
    focus_hex: tuple[int, int] | None
    commitment_age: int
    ttl_remaining: int
    replan_reason: str
    blocked_steps: int
    focus_switched: bool


@dataclass
class _UnitPlanState:
    focus_hex: tuple[int, int] | None = None
    focus_vp_id: str | None = None
    stage: str = "SETUP"
    commitment_age: int = 0
    ttl_remaining: int = 0
    blocked_steps: int = 0
    replan_reason: str = "init"
    last_step_id: int = 0


class MissionPlanner:
    """
    Lightweight multi-turn planner state.
    - Persists per-unit mission commitments (focus VP + stage + TTL)
    - Replans only on explicit gates (captured, blocked for N steps, ttl expired)
    """

    def __init__(self, default_ttl: int = 3, blocked_replan_steps: int = 2):
        self.default_ttl = int(max(1, default_ttl))
        self.blocked_replan_steps = int(max(1, blocked_replan_steps))
        self._plans: Dict[Tuple[str, str], _UnitPlanState] = {}
        self._global_step = 0

    def reset(self):
        self._plans.clear()
        self._global_step = 0

    def _ownership_for_side(self, state, side: str | None):
        if state is None or not side:
            return None
        side_to_ownership = getattr(state, "side_to_ownership", {}) or {}
        return side_to_ownership.get(str(side).upper())

    def _nearest_uncaptured_vp(self, state, side: str | None, pos):
        if state is None or not side or pos is None:
            return None, None
        points = getattr(getattr(state, "victory", None), "points", []) or []
        if not points:
            return None, None
        own_ownership = self._ownership_for_side(state, side)
        best_hex = None
        best_dist = None
        for vp in points:
            coords = getattr(vp, "hex_coords", None)
            if coords is None:
                continue
            hs = getattr(state, "hex_states", {}).get(coords)
            if hs is not None and getattr(hs, "ownership", None) == own_ownership:
                continue
            try:
                d = safe_hex_distance(pos, coords)
            except Exception:
                continue
            if best_dist is None or d < best_dist:
                best_dist = d
                best_hex = (int(coords[0]), int(coords[1]))
        return best_hex, (float(best_dist) if best_dist is not None else None)

    def _can_stepin_focus_vp_now(self, state, unit, focus_hex: tuple[int, int] | None) -> bool:
        if state is None or unit is None or focus_hex is None:
            return False
        try:
            actions = ActionCatalog(
                state,
                unit,
                terrain_config=state.game_map.terrain_config,
            ).actions()
        except Exception:
            return False
        for a in actions:
            path = getattr(a, "move_path", None) or getattr(a, "path", None)
            if not path:
                continue
            end = path[-1]
            if end is None:
                continue
            if (getattr(end, "q", None), getattr(end, "r", None)) == focus_hex:
                return True
        return False

    def _captured_for_side(self, state, side: str | None) -> int:
        if state is None or not side:
            return 0
        points = getattr(getattr(state, "victory", None), "points", []) or []
        own_ownership = self._ownership_for_side(state, side)
        if own_ownership is None:
            return 0
        captured = 0
        for vp in points:
            hs = getattr(state, "hex_states", {}).get(getattr(vp, "hex_coords", None))
            if hs is not None and getattr(hs, "ownership", None) == own_ownership:
                captured += 1
        return captured

    def _enemy_pressure_near_unit(self, state, unit, side: str | None, radius: int = 2) -> int:
        if state is None or unit is None or getattr(unit, "position", None) is None or not side:
            return 0
        side_key = str(side).upper()
        cnt = 0
        for e in getattr(state, "units", []) or []:
            if not getattr(e, "alive", False) or getattr(e, "position", None) is None:
                continue
            if str(getattr(e, "side", "")).upper() == side_key:
                continue
            try:
                if safe_hex_distance(unit.position, e.position) <= int(radius):
                    cnt += 1
            except Exception:
                continue
        return cnt

    def build_context(self, state, unit, side: str | None) -> PlannerContext:
        side_key = str(side or "").upper()
        unit_id = str(getattr(unit, "unit_id", "") or "")
        key = (side_key, unit_id)
        slot = self._plans.get(key)
        pos = getattr(unit, "position", None)

        nearest_hex, nearest_dist = self._nearest_uncaptured_vp(state, side_key, pos)
        nearest_vp_id = f"{nearest_hex[0]},{nearest_hex[1]}" if nearest_hex is not None else None

        if slot is None:
            slot = _UnitPlanState(
                focus_hex=nearest_hex,
                focus_vp_id=nearest_vp_id,
                stage="SETUP",
                commitment_age=1,
                ttl_remaining=self.default_ttl,
                blocked_steps=0,
                replan_reason="init",
            )
            self._plans[key] = slot
            focus_switched = bool(nearest_hex is not None)
        else:
            focus_switched = False
            must_replan = (
                slot.ttl_remaining <= 0
                or slot.focus_hex is None
                or slot.blocked_steps >= self.blocked_replan_steps
            )
            if must_replan and nearest_hex is not None and nearest_hex != slot.focus_hex:
                slot.focus_hex = nearest_hex
                slot.focus_vp_id = nearest_vp_id
                slot.stage = "SETUP"
                slot.commitment_age = 1
                slot.ttl_remaining = self.default_ttl
                slot.blocked_steps = 0
                slot.replan_reason = "blocked_or_expired"
                focus_switched = True
            else:
                slot.commitment_age += 1
                slot.ttl_remaining = max(0, int(slot.ttl_remaining) - 1)

        on_focus = (
            slot.focus_hex is not None
            and pos is not None
            and (getattr(pos, "q", None), getattr(pos, "r", None)) == slot.focus_hex
        )
        can_stepin = self._can_stepin_focus_vp_now(state, unit, slot.focus_hex)
        if on_focus:
            slot.stage = "HOLD"
        elif can_stepin:
            slot.stage = "STEP_IN"
        else:
            slot.stage = "SETUP"

        own_cap = self._captured_for_side(state, side_key)
        side_to_ownership = getattr(state, "side_to_ownership", {}) or {}
        other_caps = [
            self._captured_for_side(state, str(s))
            for s in side_to_ownership.keys()
            if str(s).upper() != side_key
        ]
        best_other = max(other_caps) if other_caps else 0
        pressure = self._enemy_pressure_near_unit(state, unit, side_key, radius=2)

        intent = "CAPTURE"
        if nearest_dist is None:
            intent = "ATTRIT"
        elif nearest_dist > 4:
            intent = "SETUP_CAPTURE"
        elif pressure >= 2 and own_cap >= best_other:
            intent = "DENY"
        elif pressure == 0 and own_cap > best_other + 1:
            intent = "PRESERVE"

        self._global_step += 1
        slot.last_step_id = self._global_step

        return PlannerContext(
            side=side_key,
            unit_id=unit_id,
            intent=intent,
            stage=slot.stage,
            focus_vp_id=slot.focus_vp_id,
            focus_hex=slot.focus_hex,
            commitment_age=int(slot.commitment_age),
            ttl_remaining=int(slot.ttl_remaining),
            replan_reason=str(slot.replan_reason or ""),
            blocked_steps=int(slot.blocked_steps),
            focus_switched=bool(focus_switched),
        )

    def register_outcome(self, state_after, context: PlannerContext, action) -> None:
        key = (str(context.side).upper(), str(context.unit_id))
        slot = self._plans.get(key)
        if slot is None:
            return
        path = getattr(action, "move_path", None) or getattr(action, "path", None)
        moved = bool(path)
        progressed = False
        if moved and path and slot.focus_hex is not None:
            end = path[-1]
            if end is not None:
                try:
                    d_after = safe_hex_distance(end, slot.focus_hex)
                    d_before = None
                    if getattr(action, "unit_id", None):
                        # Context before-step position is not guaranteed here; use stage hints.
                        d_before = 2 if context.stage == "STEP_IN" else 3
                    progressed = d_before is None or d_after <= d_before
                except Exception:
                    progressed = False
        if progressed:
            slot.blocked_steps = 0
            slot.replan_reason = "progress"
        else:
            slot.blocked_steps += 1
            slot.replan_reason = "no_progress"

        if slot.focus_hex is not None and state_after is not None:
            hs = getattr(state_after, "hex_states", {}).get(slot.focus_hex)
            own_ownership = self._ownership_for_side(state_after, context.side)
            if hs is not None and own_ownership is not None and getattr(hs, "ownership", None) == own_ownership:
                slot.stage = "HOLD"
                slot.replan_reason = "objective_captured"
                slot.ttl_remaining = self.default_ttl
