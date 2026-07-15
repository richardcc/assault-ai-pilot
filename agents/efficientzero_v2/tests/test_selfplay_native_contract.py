from __future__ import annotations

from types import SimpleNamespace

from agents.efficientzero_v2.core.selfplay import (
    _NativeEZV2SelfplayBackend,
    resolve_effective_step_budget,
)


class _DummyAdapter:
    def __init__(self) -> None:
        self._done = False

    def initial_state(self, scenario_id: str, seed: int = 0):
        return SimpleNamespace(
            turn=1,
            to_play="A",
            done=False,
            units=[{"unit_id": "u1", "side": "A", "q": 0, "r": 0, "hp": 10, "alive": True}],
            vp_hexes=[{"q": 1, "r": 0, "vp_id": "vp1"}],
            vp_owner_by_hex={"1,0": "B"},
        )

    def legal_actions(self):
        return ["CAPTURE:u1:1:0"] if not self._done else []

    def apply(self, action_id: str):
        self._done = True
        return SimpleNamespace(
            done=True,
            info={"damage_dealt": 0.0, "kills_dealt": 0},
            state=SimpleNamespace(end_reason="scenario_end", winner="A"),
        )

    def observation(self):
        return SimpleNamespace(
            turn=2,
            to_play="B",
            done=True,
            units=[{"unit_id": "u1", "side": "A", "q": 1, "r": 0, "hp": 10, "alive": True}],
            vp_hexes=[{"q": 1, "r": 0, "vp_id": "vp1"}],
            vp_owner_by_hex={"1,0": "A"},
        )

    def terminal(self):
        return self._done


class _LoopingAdapter:
    def __init__(self, *, unit_count: int = 2, scenario_turn_limit: int = 4) -> None:
        self._step = 0
        self._unit_count = int(unit_count)
        self._scenario_turn_limit = int(scenario_turn_limit)

    def initial_state(self, scenario_id: str, seed: int = 0):
        self._step = 0
        return self.observation()

    def scenario_max_turns(self) -> int:
        return int(self._scenario_turn_limit)

    def legal_actions(self):
        return ["MOVE:u1:0:0"]

    def apply(self, action_id: str):
        self._step += 1
        return SimpleNamespace(
            done=False,
            info={"damage_dealt": 0.0, "kills_dealt": 0},
            state=SimpleNamespace(end_reason="", winner=""),
        )

    def observation(self):
        units = [
            {"unit_id": f"u{i}", "side": "A", "q": i, "r": 0, "hp": 10, "alive": True}
            for i in range(1, max(1, self._unit_count) + 1)
        ]
        return SimpleNamespace(
            turn=int(self._step + 1),
            to_play="A",
            done=False,
            units=units,
            vp_hexes=[],
            vp_owner_by_hex={},
        )

    def terminal(self):
        return False


def test_native_selfplay_emits_contract_fields() -> None:
    backend = _NativeEZV2SelfplayBackend()
    samples = backend.play_episode(
        adapter=_DummyAdapter(),
        scenario_id="s1",
        seed=7,
        max_steps=5,
        action_dim=32,
        model=None,
    )
    assert samples
    info = dict(samples[0].info or {})
    required = (
        "legal_action_count",
        "chosen_action_prob",
        "mcts_margin",
        "objective_converted",
        "objective_progress_delta",
        "legal_reaction_options",
        "legal_capture_options",
        "action_kind",
        "terminal_reason",
    )
    for key in required:
        assert key in info


def test_resolve_effective_step_budget_precedence() -> None:
    assert resolve_effective_step_budget(
        max_steps=100,
        max_steps_override=90,
        max_turns_override=3,
        unit_count=4,
        scenario_turn_limit=8,
    ) == (12, "max_turns_override*unit_count")
    assert resolve_effective_step_budget(
        max_steps=100,
        max_steps_override=90,
        max_turns_override=0,
        unit_count=4,
        scenario_turn_limit=8,
    ) == (90, "max_steps_override")
    assert resolve_effective_step_budget(
        max_steps=100,
        max_steps_override=0,
        max_turns_override=0,
        unit_count=4,
        scenario_turn_limit=8,
    ) == (32, "scenario_turn_limit*unit_count")
    assert resolve_effective_step_budget(
        max_steps=100,
        max_steps_override=0,
        max_turns_override=0,
        unit_count=0,
        scenario_turn_limit=8,
    ) == (100, "max_steps_fallback")


def test_native_selfplay_applies_derived_scenario_budget_when_no_overrides() -> None:
    backend = _NativeEZV2SelfplayBackend()
    samples = backend.play_episode(
        adapter=_LoopingAdapter(unit_count=3, scenario_turn_limit=4),
        scenario_id="s1",
        seed=42,
        max_steps=5,
        max_steps_override=0,
        max_turns_override=0,
        action_dim=32,
        model=None,
    )
    assert len(samples) == 12
    info = dict(samples[-1].info or {})
    assert int(info.get("effective_max_steps", -1)) == 12
    assert str(info.get("step_budget_source", "")) == "scenario_turn_limit*unit_count"
    assert bool(info.get("timeout", False)) is True
    assert str(info.get("terminal_reason", "")) == "turn_unit_budget"
