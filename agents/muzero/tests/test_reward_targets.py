from dataclasses import dataclass

from agents.muzero.core.selfplay import shaped_training_reward, training_reward_from_transition


@dataclass
class _State:
    winner: str | None


@dataclass
class _Transition:
    done: bool
    state: _State
    action_id: str = ""


def test_training_reward_win_for_root_side():
    tr = _Transition(done=True, state=_State(winner="SIDE_A"))
    assert training_reward_from_transition("SIDE_A", tr) == 1.0


def test_training_reward_loss_for_root_side():
    tr = _Transition(done=True, state=_State(winner="SIDE_B"))
    assert training_reward_from_transition("SIDE_A", tr) == -1.0


def test_training_reward_non_terminal_is_zero():
    tr = _Transition(done=False, state=_State(winner=None))
    assert training_reward_from_transition("SIDE_A", tr) == 0.0


def test_shaped_reward_adds_vp_capture_event_bonus():
    tr = _Transition(done=False, state=_State(winner=None), action_id="MOVE:U1:1:1")
    total, comp = shaped_training_reward(
        root_to_play="SIDE_A",
        transition=tr,
        action_kind="MOVE",
        damage_dealt=0.0,
        kills_dealt=0,
        vp_captures=2,
        vp_net_delta=1,
        reward_shaping={
            "vp_capture_bonus_per_hex": 0.5,
            "vp_net_gain_bonus": 0.25,
            "idle_penalty": 0.0,
        },
    )
    assert comp["vp_capture_event"] == 1.0
    assert comp["vp_net_gain"] == 0.25
    assert comp["vp_net_loss"] == 0.0
    assert total == 1.25


def test_shaped_reward_applies_vp_net_loss_penalty():
    tr = _Transition(done=False, state=_State(winner=None), action_id="MOVE:U1:1:1")
    total, comp = shaped_training_reward(
        root_to_play="SIDE_A",
        transition=tr,
        action_kind="MOVE",
        damage_dealt=0.0,
        kills_dealt=0,
        vp_captures=0,
        vp_net_delta=-2,
        reward_shaping={
            "vp_net_loss_penalty": 0.1,
            "idle_penalty": 0.0,
        },
    )
    assert comp["vp_capture_event"] == 0.0
    assert comp["vp_net_gain"] == 0.0
    assert comp["vp_net_loss"] == 0.2
    assert total == -0.2


def test_shaped_reward_penalizes_failed_opportunity_fire():
    tr = _Transition(done=False, state=_State(winner=None), action_id="OPPORTUNITY_FIRE:IT_1:US_1")
    total, comp = shaped_training_reward(
        root_to_play="SIDE_A",
        transition=tr,
        action_kind="OPPORTUNITY_FIRE",
        damage_dealt=0.0,
        kills_dealt=0,
        reward_shaping={
            "reaction_fire_miss_penalty": 0.08,
            "idle_penalty": 0.0,
        },
    )
    assert comp["reaction_fire_miss"] == -0.08
    assert total == -0.08


def test_shaped_reward_no_penalty_if_opportunity_fire_hits():
    tr = _Transition(done=False, state=_State(winner=None), action_id="OPPORTUNITY_FIRE:IT_1:US_1")
    total, comp = shaped_training_reward(
        root_to_play="SIDE_A",
        transition=tr,
        action_kind="OPPORTUNITY_FIRE",
        damage_dealt=1.0,
        kills_dealt=0,
        reward_shaping={
            "reaction_fire_miss_penalty": 0.08,
            "damage_weight": 0.04,
            "idle_penalty": 0.0,
        },
    )
    assert comp["reaction_fire_miss"] == 0.0
    assert total == 0.04
