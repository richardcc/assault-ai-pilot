from __future__ import annotations

from types import SimpleNamespace

from agents.efficientzero_v2.core.selfplay import _NativeEZV2SelfplayBackend


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
