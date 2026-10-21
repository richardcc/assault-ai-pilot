import math
import pytest
from types import SimpleNamespace

from agents.efficientzero_v2.core.selfplay import (
    resolve_effective_step_budget,
    _scenario_total_units_from_adapter,
    _NativeEZV2SelfplayBackend,
)
from agents.efficientzero_v2.core.adapter_voec import EZV2VOECAdapter, EZV2Observation


def test_resolve_effective_step_budget_with_multiplier():
    # 1. Standard scenario budget with steps_per_unit_turn headroom
    steps, source = resolve_effective_step_budget(
        max_steps=100,
        max_steps_override=0,
        max_turns_override=0,
        unit_count=10,
        scenario_turn_limit=8,
        steps_per_unit_turn=2.5,
    )
    assert steps == int(math.ceil(8 * 10 * 2.5))  # 200
    assert source == "scenario_turn_limit*unit_count"

    # 2. Max turns override with multiplier
    steps_ov, source_ov = resolve_effective_step_budget(
        max_steps=100,
        max_steps_override=0,
        max_turns_override=4,
        unit_count=6,
        scenario_turn_limit=8,
        steps_per_unit_turn=3.0,
    )
    assert steps_ov == int(math.ceil(4 * 6 * 3.0))  # 72
    assert source_ov == "max_turns_override*unit_count"

    # 3. Explicit max_steps_override (when max_turns_override is 0)
    steps_fixed, source_fixed = resolve_effective_step_budget(
        max_steps=100,
        max_steps_override=45,
        max_turns_override=0,
        unit_count=6,
        scenario_turn_limit=8,
        steps_per_unit_turn=3.0,
    )
    assert steps_fixed == 45
    assert source_fixed == "max_steps_override"

    # 4. Fallback when unit_count or turn_limit is 0
    steps_fb, source_fb = resolve_effective_step_budget(
        max_steps=80,
        max_steps_override=0,
        max_turns_override=0,
        unit_count=0,
        scenario_turn_limit=8,
        steps_per_unit_turn=2.5,
    )
    assert steps_fb == 80
    assert source_fb == "max_steps_fallback"


def test_scenario_total_units_from_adapter():
    class DummySim:
        def scenario_total_units(self):
            return 18

    class DummyAdapter:
        def __init__(self):
            self.sim = DummySim()

        def scenario_total_units(self):
            return self.sim.scenario_total_units()

    adapter = DummyAdapter()
    assert _scenario_total_units_from_adapter(adapter, default_units=5) == 18

    # When adapter doesn't implement scenario_total_units, default is returned
    class FallbackAdapter:
        pass

    assert _scenario_total_units_from_adapter(FallbackAdapter(), default_units=7) == 7


class _DynamicBudgetMockAdapter:
    def __init__(self, initial_units: int = 4, total_units: int = 12, max_turns: int = 6):
        self._initial_units = initial_units
        self._total_units = total_units
        self._max_turns = max_turns
        self.step_counter = 0
        self.current_turn = 1

    def scenario_max_turns(self) -> int:
        return self._max_turns

    def scenario_total_units(self) -> int:
        return self._total_units

    def initial_state(self, scenario_id: str = "test", seed: int = 0):
        self.step_counter = 0
        self.current_turn = 1
        return EZV2Observation(
            turn=1,
            to_play="US",
            done=False,
            units=[{"unit_id": f"u{i}", "side": "US", "alive": True, "hp": 10} for i in range(self._initial_units)],
            playable_hexes=[],
            vp_hexes=[],
            vp_owner_by_hex={},
            max_turns=self._max_turns,
        )

    def legal_actions(self):
        return ["PASS:u0"]

    def apply(self, action_id: str):
        self.step_counter += 1
        # Advance turn every 5 steps
        if self.step_counter % 5 == 0:
            self.current_turn += 1
        done = self.current_turn > self._max_turns
        return SimpleNamespace(
            action_id=action_id,
            reward=0.0,
            done=done,
            info={},
            state=SimpleNamespace(turn=self.current_turn, end_reason="turn_limit" if done else ""),
        )

    def observation(self):
        done = self.current_turn > self._max_turns
        return EZV2Observation(
            turn=self.current_turn,
            to_play="US",
            done=done,
            units=[{"unit_id": f"u{i}", "side": "US", "alive": True, "hp": 10} for i in range(self._initial_units)],
            playable_hexes=[],
            vp_hexes=[],
            vp_owner_by_hex={},
            max_turns=self._max_turns,
        )

    def terminal(self) -> bool:
        return self.current_turn > self._max_turns


def test_selfplay_allocates_budget_based_on_total_reinforcements():
    adapter = _DynamicBudgetMockAdapter(initial_units=4, total_units=12, max_turns=6)
    backend = _NativeEZV2SelfplayBackend()
    samples = backend.play_episode(
        adapter=adapter,
        scenario_id="mock_reinf_scenario",
        seed=123,
        steps_per_unit_turn=2.0,
    )
    assert len(samples) > 0
    last_info = samples[-1].info
    # Budget should be computed using total_units (12) * max_turns (6) * steps_per_unit_turn (2.0) = 144
    assert int(last_info.get("effective_max_steps", 0)) == 144
    # The game advanced to turn 7 and terminated naturally by turn limit (not timeout)
    assert last_info.get("timeout") is False
    assert adapter.terminal() is True


class _DeadlockMockAdapter:
    def __init__(self):
        self.step_counter = 0

    def scenario_max_turns(self) -> int:
        return 8

    def scenario_total_units(self) -> int:
        return 4

    def initial_state(self, scenario_id: str = "test", seed: int = 0):
        self.step_counter = 0
        return EZV2Observation(
            turn=1,
            to_play="US",
            done=False,
            units=[{"unit_id": f"u{i}", "side": "US", "alive": True, "hp": 10} for i in range(4)],
            playable_hexes=[],
            vp_hexes=[],
            vp_owner_by_hex={},
            max_turns=8,
        )

    def legal_actions(self):
        return ["PASS:u0"]

    def apply(self, action_id: str):
        self.step_counter += 1
        # Never advances turn! Simulates a deadlock within turn 1.
        return SimpleNamespace(
            action_id=action_id,
            reward=0.0,
            done=False,
            info={},
            state=SimpleNamespace(turn=1, end_reason=""),
        )

    def observation(self):
        return EZV2Observation(
            turn=1,
            to_play="US",
            done=False,
            units=[{"unit_id": f"u{i}", "side": "US", "alive": True, "hp": 10} for i in range(4)],
            playable_hexes=[],
            vp_hexes=[],
            vp_owner_by_hex={},
            max_turns=8,
        )

    def terminal(self) -> bool:
        return False


def test_selfplay_deadlock_watchdog_catches_infinite_turn_loop():
    adapter = _DeadlockMockAdapter()
    backend = _NativeEZV2SelfplayBackend()
    samples = backend.play_episode(
        adapter=adapter,
        scenario_id="mock_deadlock_scenario",
        seed=999,
        steps_per_unit_turn=2.0,
    )
    assert len(samples) > 0
    last_info = samples[-1].info
    assert last_info.get("timeout") is True
    assert last_info.get("terminal_reason") == "turn_deadlock_watchdog"
