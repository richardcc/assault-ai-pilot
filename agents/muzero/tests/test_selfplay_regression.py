from dataclasses import dataclass
from types import SimpleNamespace

from agents.muzero.core.selfplay import play_episode


@dataclass
class _Obs:
    turn: int
    to_play: str | None
    done: bool
    units: list[dict]
    playable_hexes: list[dict]
    vp_hexes: list[dict]
    vp_owner_by_hex: dict[str, str]
    terrain_move_cost_by_hex: dict[str, float]
    terrain_cover_by_hex: dict[str, float]
    terrain_los_block_by_hex: dict[str, int]


class _AdapterStub:
    def __init__(self):
        self.sim = None
        self._initial_obs = _Obs(
            turn=1,
            to_play="RED",
            done=False,
            units=[
                {"unit_id": "U1", "side": "RED", "q": 0, "r": 0, "hp": 10, "alive": True},
                {"unit_id": "U2", "side": "BLUE", "q": 1, "r": 0, "hp": 10, "alive": True},
            ],
            playable_hexes=[{"q": 0, "r": 0}, {"q": 1, "r": 0}],
            vp_hexes=[{"q": 1, "r": 0}],
            vp_owner_by_hex={"1,0": "BLUE"},
            terrain_move_cost_by_hex={},
            terrain_cover_by_hex={},
            terrain_los_block_by_hex={},
        )
        self._post_obs = _Obs(
            turn=2,
            to_play="BLUE",
            done=True,
            units=[
                {"unit_id": "U1", "side": "RED", "q": 0, "r": 0, "hp": 10, "alive": True},
                {"unit_id": "U2", "side": "BLUE", "q": 1, "r": 0, "hp": 10, "alive": True},
            ],
            playable_hexes=[{"q": 0, "r": 0}, {"q": 1, "r": 0}],
            vp_hexes=[{"q": 1, "r": 0}],
            vp_owner_by_hex={"1,0": "RED"},
            terrain_move_cost_by_hex={},
            terrain_cover_by_hex={},
            terrain_los_block_by_hex={},
        )
        self._done = False

    def initial_state(self, scenario_id: str, seed: int = 0):
        self._done = False
        return self._initial_obs

    def legal_actions(self):
        return ["MOVE:U1:1:0"] if not self._done else []

    def apply(self, action_id: str):
        self._done = True
        state = SimpleNamespace(
            units=[
                SimpleNamespace(unit_id="U1", side="RED", hp=10, alive=True),
                SimpleNamespace(unit_id="U2", side="BLUE", hp=10, alive=True),
            ],
            turn=2,
            to_play="BLUE",
            end_reason="test_end",
            winner="RED",
        )
        return SimpleNamespace(done=True, state=state, info={"runtime_events": []})

    def observation(self):
        return self._post_obs if self._done else self._initial_obs

    def terminal(self):
        return self._done


def test_play_episode_vp_summary_vars_are_initialized_before_use():
    adapter = _AdapterStub()

    samples = play_episode(
        adapter=adapter,
        scenario_id="stub_scenario",
        seed=123,
        max_steps=1,
        mcts_simulations=1,
        collect_xai=False,
    )

    assert len(samples) == 1
    info = samples[0].info
    assert int(info["vp_captures"]) == 1
    assert int(info["objective_had_opportunity"]) in {0, 1}
