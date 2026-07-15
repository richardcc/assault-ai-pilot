import json
from types import SimpleNamespace

from assault_sim.training_env import TrainingEnv


class _DummyReward:
    def reset(self, _state):
        return None

    def compute(self, **_kwargs):
        return 0.0


class _DummyAction:
    def __init__(self, unit_id: str):
        self.unit_id = unit_id


def _unit(unit_id: str, side, hp: int, alive: bool):
    return SimpleNamespace(
        unit_id=unit_id,
        side=side,
        hp=hp,
        alive=alive,
        position=SimpleNamespace(q=0, r=0),
    )


def test_damage_and_kills_are_attributed_to_rl_side_with_enum_like_side(tmp_path, monkeypatch):
    # Regression: actor.side may be enum-like (with .value), while rl_side is a str.
    # Damage/kill attribution must still go to rl_* buckets for RL actions.
    cfg_path = tmp_path / "env_config.json"
    cfg_path.write_text(json.dumps({"environment": {}}), encoding="utf-8")

    side_rl = SimpleNamespace(value="US")
    side_enemy = SimpleNamespace(value="GE")
    actor_before = _unit("US_1", side_rl, hp=3, alive=True)
    enemy_before = _unit("GE_1", side_enemy, hp=2, alive=True)
    actor_after = _unit("US_1", side_rl, hp=3, alive=True)
    enemy_after = _unit("GE_1", side_enemy, hp=0, alive=False)

    state_before = SimpleNamespace(
        units=[actor_before, enemy_before],
        turn=1,
        victory=SimpleNamespace(points=[]),
        side_to_ownership={},
        hex_states={},
        done=False,
    )
    state_after = SimpleNamespace(
        units=[actor_after, enemy_after],
        turn=1,
        victory=SimpleNamespace(points=[]),
        side_to_ownership={},
        hex_states={},
        done=False,
    )

    sim = SimpleNamespace(
        game_state=state_before,
        scenario=SimpleNamespace(max_turns=10, victory_outcomes={}),
    )

    def _sim_step(_action):
        sim.game_state = state_after
        return state_after, 0.0, False, {}

    sim.step = _sim_step

    monkeypatch.setattr("assault_sim.training_env.encode_state", lambda **_kwargs: {"obs": "ok"})

    env = TrainingEnv(
        sim_env=sim,
        env_config_path=cfg_path,
        rl_side="US",
        reward_fn=_DummyReward(),
    )
    action = _DummyAction("US_1")  # class name marks this as a ranged attack

    _obs, _reward, _done, info = env.step(action)

    assert info["rl_damage"] == 2
    assert info["rl_kills"] == 1
    assert info["enemy_damage"] == 0
    assert info["enemy_kills"] == 0
