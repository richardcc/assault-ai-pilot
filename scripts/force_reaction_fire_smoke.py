from __future__ import annotations

from types import SimpleNamespace

from assault_model.actions.movement import MoveAction
from assault_model.map.hex_coord import HexCoord
from assault_model.runtime.execution_context import ExecutionContext
from assault_model.runtime.game_state_runtime import RuntimeGameState
from assault_model.runtime import game_state_runtime as rt_mod


def _unit(unit_id: str, side: str, q: int, r: int):
    return SimpleNamespace(
        unit_id=unit_id,
        side=side,
        alive=True,
        suppressed=False,
        fallback=False,
        can_fire=True,
        position=HexCoord(q, r),
        unit_type=SimpleNamespace(_resolve_attack_mode=lambda _distance: "DIRECT_FIRE"),
    )


def _build_runtime(units):
    base_state = SimpleNamespace(
        turn=1,
        units=list(units),
        _cache_version=0,
        game_map=SimpleNamespace(),
        hex_states={},
        side_to_ownership={},
        victory=None,
        vp_tracker=None,
        done=False,
        winner=None,
        end_reason=None,
    )
    base_state.recalculate_hex_control = lambda: None
    scenario = SimpleNamespace(terrain_config=SimpleNamespace(), max_turns=None, victory_outcomes={})
    return RuntimeGameState(base_state, scenario)


class _ResolutionResult:
    def __init__(self, state):
        self.new_state = state
        self.combat_result = None


class _Bus:
    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(event)


def main() -> int:
    us = _unit("US_1", "US", 0, 0)
    it = _unit("IT_1", "IT", 2, 0)
    runtime = _build_runtime([us, it])
    runtime.side_controller_map = {"US": "ai", "IT": "ai"}

    prev_resolve_action = rt_mod.resolve_action
    prev_update_spotting = rt_mod.update_spotting
    prev_has_los = rt_mod.has_line_of_sight
    prev_enabled = rt_mod.REACTION_FIRE_ENABLED

    bus = _Bus()
    ctx = ExecutionContext(event_bus=bus, game_map=SimpleNamespace())

    def fake_resolve_action(state, action, combat_result=None, context=None):
        if isinstance(action, MoveAction):
            mover = next(u for u in state.units if u.unit_id == action.unit_id)
            mover.position = action.path[-1]
        return _ResolutionResult(state)

    try:
        rt_mod.resolve_action = fake_resolve_action
        rt_mod.update_spotting = lambda *_args, **_kwargs: None
        rt_mod.has_line_of_sight = lambda **_kwargs: True
        rt_mod.REACTION_FIRE_ENABLED = True

        runtime.apply_action(MoveAction("US_1", [HexCoord(1, 0)]), context=ctx)
        reaction_events = [e for e in bus.events if str(e.get("type", "")).upper() == "REACTION_FIRE"]
        count = len(reaction_events)
        print(f"forced_reaction_fire_count={count}")
        return 0 if count > 0 else 1
    finally:
        rt_mod.resolve_action = prev_resolve_action
        rt_mod.update_spotting = prev_update_spotting
        rt_mod.has_line_of_sight = prev_has_los
        rt_mod.REACTION_FIRE_ENABLED = prev_enabled


if __name__ == "__main__":
    raise SystemExit(main())

