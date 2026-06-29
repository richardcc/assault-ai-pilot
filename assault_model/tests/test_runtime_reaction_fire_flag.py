from types import SimpleNamespace

from assault_model.actions.movement import MoveAction
from assault_model.actions.ranged_direct import RangedDirectAttack
from assault_model.map.hex_coord import HexCoord
from assault_model.runtime import game_state_runtime as rt_mod
from assault_model.runtime.execution_context import ExecutionContext
from assault_model.runtime.game_state_runtime import RuntimeGameState


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


def test_reaction_fire_disabled_by_default(monkeypatch):
    us = _unit("US_1", "US", 0, 0)
    it = _unit("IT_1", "IT", 2, 0)
    rt = _build_runtime([us, it])

    calls = []

    def fake_resolve_action(state, action, combat_result=None, context=None):
        calls.append(type(action).__name__)
        if isinstance(action, MoveAction):
            mover = next(u for u in state.units if u.unit_id == action.unit_id)
            mover.position = action.path[-1]
        return _ResolutionResult(state)

    monkeypatch.setattr(rt_mod, "resolve_action", fake_resolve_action)
    monkeypatch.setattr(rt_mod, "update_spotting", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(rt_mod, "has_line_of_sight", lambda **_kwargs: True)
    monkeypatch.setattr(rt_mod, "REACTION_FIRE_ENABLED", False)

    move = MoveAction("US_1", [HexCoord(1, 0)])
    rt.apply_action(move)

    assert calls == ["MoveAction"]
    assert rt.reaction_used_this_turn == set()


def test_reaction_fire_once_per_reactor_per_turn(monkeypatch):
    us1 = _unit("US_1", "US", 0, 0)
    us2 = _unit("US_2", "US", 0, 1)
    it = _unit("IT_1", "IT", 2, 0)
    rt = _build_runtime([us1, us2, it])

    calls = []

    def fake_resolve_action(state, action, combat_result=None, context=None):
        calls.append(type(action).__name__)
        if isinstance(action, MoveAction):
            mover = next(u for u in state.units if u.unit_id == action.unit_id)
            mover.position = action.path[-1]
        elif isinstance(action, RangedDirectAttack):
            target = next(u for u in state.units if u.unit_id == action.target_id)
            target.hit_by_reaction = True
        return _ResolutionResult(state)

    monkeypatch.setattr(rt_mod, "resolve_action", fake_resolve_action)
    monkeypatch.setattr(rt_mod, "update_spotting", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(rt_mod, "has_line_of_sight", lambda **_kwargs: True)
    monkeypatch.setattr(rt_mod, "REACTION_FIRE_ENABLED", True)

    rt.apply_action(MoveAction("US_1", [HexCoord(1, 0)]))
    rt.apply_action(MoveAction("US_2", [HexCoord(1, 1)]))

    # First move triggers one reaction shot; second move does not (same reactor already used).
    assert calls.count("RangedDirectAttack") == 1
    assert "IT_1" in rt.reaction_used_this_turn
    assert "IT_1" in rt.activated_units


def test_reactor_cannot_react_if_already_activated(monkeypatch):
    us = _unit("US_1", "US", 0, 0)
    it = _unit("IT_1", "IT", 2, 0)
    rt = _build_runtime([us, it])
    rt.activated_units.add("IT_1")

    calls = []

    def fake_resolve_action(state, action, combat_result=None, context=None):
        calls.append(type(action).__name__)
        if isinstance(action, MoveAction):
            mover = next(u for u in state.units if u.unit_id == action.unit_id)
            mover.position = action.path[-1]
        return _ResolutionResult(state)

    monkeypatch.setattr(rt_mod, "resolve_action", fake_resolve_action)
    monkeypatch.setattr(rt_mod, "update_spotting", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(rt_mod, "has_line_of_sight", lambda **_kwargs: True)
    monkeypatch.setattr(rt_mod, "REACTION_FIRE_ENABLED", True)
    rt.apply_action(MoveAction("US_1", [HexCoord(1, 0)]))

    # Reactor already activated: reaction must be blocked.
    assert calls.count("RangedDirectAttack") == 0


def test_reaction_fire_event_emitted_before_unit_moved(monkeypatch):
    us = _unit("US_1", "US", 0, 0)
    it = _unit("IT_1", "IT", 2, 0)
    rt = _build_runtime([us, it])

    def fake_resolve_action(state, action, combat_result=None, context=None):
        if isinstance(action, MoveAction):
            mover = next(u for u in state.units if u.unit_id == action.unit_id)
            mover.position = action.path[-1]
        return _ResolutionResult(state)

    class _Bus:
        def __init__(self):
            self.events = []

        def emit(self, event):
            self.events.append(event)

    bus = _Bus()
    ctx = ExecutionContext(event_bus=bus, game_map=SimpleNamespace())

    monkeypatch.setattr(rt_mod, "resolve_action", fake_resolve_action)
    monkeypatch.setattr(rt_mod, "update_spotting", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(rt_mod, "has_line_of_sight", lambda **_kwargs: True)
    monkeypatch.setattr(rt_mod, "REACTION_FIRE_ENABLED", True)

    rt.apply_action(MoveAction("US_1", [HexCoord(1, 0)]), context=ctx)

    event_types = [e.get("type") for e in bus.events]
    assert "REACTION_FIRE" in event_types
    assert "UNIT_MOVED" in event_types
    assert event_types.index("REACTION_FIRE") < event_types.index("UNIT_MOVED")


def test_human_reaction_creates_pending_window(monkeypatch):
    us = _unit("US_1", "US", 0, 0)
    it = _unit("IT_1", "IT", 2, 0)
    rt = _build_runtime([us, it])
    rt.side_controller_map = {"IT": "human", "US": "ai"}

    def fake_resolve_action(state, action, combat_result=None, context=None):
        if isinstance(action, MoveAction):
            mover = next(u for u in state.units if u.unit_id == action.unit_id)
            mover.position = action.path[-1]
        return _ResolutionResult(state)

    monkeypatch.setattr(rt_mod, "resolve_action", fake_resolve_action)
    monkeypatch.setattr(rt_mod, "update_spotting", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(rt_mod, "has_line_of_sight", lambda **_kwargs: True)
    monkeypatch.setattr(rt_mod, "REACTION_FIRE_ENABLED", True)

    rt.apply_action(MoveAction("US_1", [HexCoord(1, 0)]))
    assert rt.pending_reaction is not None
    assert rt.pending_reaction.get("reactor_id") == "IT_1"
    assert rt.pending_reaction.get("target_id") == "US_1"
    assert "IT_1" not in rt.reaction_used_this_turn


def test_ai_reactor_auto_executes_without_pending_window(monkeypatch):
    us = _unit("US_1", "US", 0, 0)
    it = _unit("IT_1", "IT", 2, 0)
    rt = _build_runtime([us, it])
    rt.side_controller_map = {"IT": "ai", "US": "human"}

    calls = []

    def fake_resolve_action(state, action, combat_result=None, context=None):
        calls.append(type(action).__name__)
        if isinstance(action, MoveAction):
            mover = next(u for u in state.units if u.unit_id == action.unit_id)
            mover.position = action.path[-1]
        return _ResolutionResult(state)

    monkeypatch.setattr(rt_mod, "resolve_action", fake_resolve_action)
    monkeypatch.setattr(rt_mod, "update_spotting", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(rt_mod, "has_line_of_sight", lambda **_kwargs: True)
    monkeypatch.setattr(rt_mod, "REACTION_FIRE_ENABLED", True)

    rt.apply_action(MoveAction("US_1", [HexCoord(1, 0)]))
    assert rt.pending_reaction is None
    assert calls.count("RangedDirectAttack") == 1


def test_ai_reactor_can_skip_by_decision(monkeypatch):
    us = _unit("US_1", "US", 0, 0)
    it = _unit("IT_1", "IT", 2, 0)
    rt = _build_runtime([us, it])
    rt.side_controller_map = {"IT": "ai", "US": "human"}

    calls = []

    def fake_resolve_action(state, action, combat_result=None, context=None):
        calls.append(type(action).__name__)
        if isinstance(action, MoveAction):
            mover = next(u for u in state.units if u.unit_id == action.unit_id)
            mover.position = action.path[-1]
        return _ResolutionResult(state)

    monkeypatch.setattr(rt_mod, "resolve_action", fake_resolve_action)
    monkeypatch.setattr(rt_mod, "update_spotting", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(rt_mod, "has_line_of_sight", lambda **_kwargs: True)
    monkeypatch.setattr(rt_mod, "REACTION_FIRE_ENABLED", True)
    monkeypatch.setattr(
        RuntimeGameState,
        "_should_ai_use_reaction",
        lambda self, reactor, target: False,
    )

    rt.apply_action(MoveAction("US_1", [HexCoord(1, 0)]))
    assert rt.pending_reaction is None
    assert calls.count("RangedDirectAttack") == 0
    assert "IT_1" not in rt.reaction_used_this_turn


def test_ai_reactor_policy_never_skips(monkeypatch):
    us = _unit("US_1", "US", 0, 0)
    it = _unit("IT_1", "IT", 2, 0)
    rt = _build_runtime([us, it])
    rt.side_controller_map = {"IT": "ai", "US": "human"}

    calls = []

    def fake_resolve_action(state, action, combat_result=None, context=None):
        calls.append(type(action).__name__)
        if isinstance(action, MoveAction):
            mover = next(u for u in state.units if u.unit_id == action.unit_id)
            mover.position = action.path[-1]
        return _ResolutionResult(state)

    monkeypatch.setattr(rt_mod, "resolve_action", fake_resolve_action)
    monkeypatch.setattr(rt_mod, "update_spotting", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(rt_mod, "has_line_of_sight", lambda **_kwargs: True)
    monkeypatch.setattr(rt_mod, "REACTION_FIRE_ENABLED", True)
    monkeypatch.setattr(rt_mod, "AI_REACTION_POLICY", "never")

    rt.apply_action(MoveAction("US_1", [HexCoord(1, 0)]))
    assert calls.count("RangedDirectAttack") == 0


def test_ai_reactor_policy_always_uses(monkeypatch):
    us = _unit("US_1", "US", 0, 0)
    it = _unit("IT_1", "IT", 2, 0)
    rt = _build_runtime([us, it])
    rt.side_controller_map = {"IT": "ai", "US": "human"}

    calls = []

    def fake_resolve_action(state, action, combat_result=None, context=None):
        calls.append(type(action).__name__)
        if isinstance(action, MoveAction):
            mover = next(u for u in state.units if u.unit_id == action.unit_id)
            mover.position = action.path[-1]
        return _ResolutionResult(state)

    monkeypatch.setattr(rt_mod, "resolve_action", fake_resolve_action)
    monkeypatch.setattr(rt_mod, "update_spotting", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(rt_mod, "has_line_of_sight", lambda **_kwargs: True)
    monkeypatch.setattr(rt_mod, "REACTION_FIRE_ENABLED", True)
    monkeypatch.setattr(rt_mod, "AI_REACTION_POLICY", "always")

    rt.apply_action(MoveAction("US_1", [HexCoord(1, 0)]))
    assert calls.count("RangedDirectAttack") == 1


def test_resolve_pending_reaction_use_and_skip(monkeypatch):
    us = _unit("US_1", "US", 0, 0)
    it = _unit("IT_1", "IT", 2, 0)
    rt = _build_runtime([us, it])
    rt.side_controller_map = {"IT": "human", "US": "ai"}

    calls = []

    def fake_resolve_action(state, action, combat_result=None, context=None):
        calls.append(type(action).__name__)
        if isinstance(action, MoveAction):
            mover = next(u for u in state.units if u.unit_id == action.unit_id)
            mover.position = action.path[-1]
        return _ResolutionResult(state)

    monkeypatch.setattr(rt_mod, "resolve_action", fake_resolve_action)
    monkeypatch.setattr(rt_mod, "update_spotting", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(rt_mod, "has_line_of_sight", lambda **_kwargs: True)
    monkeypatch.setattr(rt_mod, "REACTION_FIRE_ENABLED", True)

    rt.apply_action(MoveAction("US_1", [HexCoord(1, 0)]))
    out_use = rt.resolve_pending_reaction(use_reaction=True)
    assert out_use.get("resolved") is True
    assert out_use.get("used") is True
    assert "RangedDirectAttack" in calls
    assert "IT_1" in rt.reaction_used_this_turn

    rt.pending_reaction = {"reactor_id": "IT_1", "target_id": "US_1", "trigger": "ENEMY_MOVES_IN_LOS"}
    out_skip = rt.resolve_pending_reaction(use_reaction=False)
    assert out_skip.get("resolved") is True
    assert out_skip.get("used") is False
