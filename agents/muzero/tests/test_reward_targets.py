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


def test_shaped_reward_opportunity_no_progress_penalty_is_effective():
    tr = _Transition(done=False, state=_State(winner=None), action_id="OPPORTUNITY_FIRE:IT_1:US_1")
    total, comp = shaped_training_reward(
        root_to_play="IT",
        transition=tr,
        action_kind="OPPORTUNITY_FIRE",
        damage_dealt=0.0,
        kills_dealt=0,
        objective_had_opportunity=True,
        objective_progress_delta=0.0,
        reward_shaping={
            "objective_no_progress_penalty": 0.17,
            "objective_no_progress_attack_penalty": 0.24,
            "idle_penalty": 0.0,
        },
    )
    assert comp["objective_progress"] == 0.0
    assert comp["objective_no_progress"] == -0.17
    assert comp["objective_no_progress_attack"] == -0.24
    assert total == -0.41


def test_shaped_reward_opportunity_skip_avoids_attack_no_progress_penalty():
    tr = _Transition(done=False, state=_State(winner=None), action_id="OPPORTUNITY_SKIP:IT_1:US_1")
    total, comp = shaped_training_reward(
        root_to_play="IT",
        transition=tr,
        action_kind="OPPORTUNITY_SKIP",
        damage_dealt=0.0,
        kills_dealt=0,
        objective_had_opportunity=True,
        objective_progress_delta=0.0,
        reward_shaping={
            "objective_no_progress_penalty": 0.17,
            "objective_no_progress_attack_penalty": 0.24,
            "idle_penalty": 0.0,
        },
    )
    assert comp["objective_no_progress"] == -0.17
    assert comp["objective_no_progress_attack"] == 0.0
    assert total == -0.17


def test_shaped_reward_progress_and_conversion_outweigh_no_progress_path():
    tr = _Transition(done=False, state=_State(winner=None), action_id="CAPTURE:IT_1:2:0")
    progress_total, progress_comp = shaped_training_reward(
        root_to_play="IT",
        transition=tr,
        action_kind="CAPTURE",
        damage_dealt=0.0,
        kills_dealt=0,
        vp_captures=1,
        vp_net_delta=1,
        objective_had_opportunity=True,
        objective_progress_delta=1.0,
        reward_shaping={
            "vp_capture_bonus_per_hex": 1.15,
            "vp_net_gain_bonus": 0.30,
            "objective_progress_bonus_per_hex": 0.44,
            "objective_no_progress_penalty": 0.17,
            "objective_no_progress_attack_penalty": 0.24,
            "idle_penalty": 0.0,
        },
    )
    stall_total, stall_comp = shaped_training_reward(
        root_to_play="IT",
        transition=tr,
        action_kind="OPPORTUNITY_FIRE",
        damage_dealt=0.0,
        kills_dealt=0,
        vp_captures=0,
        vp_net_delta=0,
        objective_had_opportunity=True,
        objective_progress_delta=0.0,
        reward_shaping={
            "vp_capture_bonus_per_hex": 1.15,
            "vp_net_gain_bonus": 0.30,
            "objective_progress_bonus_per_hex": 0.44,
            "objective_no_progress_penalty": 0.17,
            "objective_no_progress_attack_penalty": 0.24,
            "idle_penalty": 0.0,
        },
    )
    assert progress_comp["vp_capture_event"] == 1.15
    assert progress_comp["objective_progress"] == 0.44
    assert stall_comp["objective_no_progress"] == -0.17
    assert stall_comp["objective_no_progress_attack"] == -0.24
    assert progress_total > stall_total


def test_shaped_reward_prefers_opportunity_skip_to_preserve_near_vp_capture():
    tr = _Transition(done=False, state=_State(winner=None), action_id="OPPORTUNITY_SKIP:IT_1:US_1")
    skip_total, skip_comp = shaped_training_reward(
        root_to_play="IT",
        transition=tr,
        action_kind="OPPORTUNITY_SKIP",
        damage_dealt=0.0,
        kills_dealt=0,
        objective_had_opportunity=True,
        objective_progress_delta=0.0,
        objective_distance_before=1.0,
        legal_capture_options=0,
        reward_shaping={
            "opportunity_skip_capture_preserve_bonus": 0.07,
            "opportunity_vp_distance_threshold": 2.0,
            "idle_penalty": 0.0,
        },
    )
    fire_total, fire_comp = shaped_training_reward(
        root_to_play="IT",
        transition=tr,
        action_kind="OPPORTUNITY_FIRE",
        damage_dealt=0.0,
        kills_dealt=0,
        objective_had_opportunity=True,
        objective_progress_delta=0.0,
        objective_distance_before=1.0,
        legal_capture_options=0,
        reward_shaping={
            "opportunity_fire_no_progress_penalty": 0.11,
            "opportunity_vp_distance_threshold": 2.0,
            "idle_penalty": 0.0,
        },
    )
    assert skip_comp["opportunity_skip_capture_preserve"] == 0.07
    assert fire_comp["opportunity_fire_no_progress"] == -0.11
    assert skip_total > fire_total


def test_shaped_reward_keeps_opportunity_fire_when_tactically_strong():
    tr = _Transition(done=False, state=_State(winner=None), action_id="OPPORTUNITY_FIRE:IT_1:US_1")
    fire_total, fire_comp = shaped_training_reward(
        root_to_play="IT",
        transition=tr,
        action_kind="OPPORTUNITY_FIRE",
        damage_dealt=2.0,
        kills_dealt=1,
        objective_had_opportunity=True,
        objective_progress_delta=0.2,
        objective_distance_before=1.0,
        legal_capture_options=0,
        reward_shaping={
            "damage_weight": 0.08,
            "kill_weight": 0.30,
            "opportunity_fire_no_progress_penalty": 0.20,
            "opportunity_vp_distance_threshold": 2.0,
            "idle_penalty": 0.0,
        },
    )
    skip_total, skip_comp = shaped_training_reward(
        root_to_play="IT",
        transition=tr,
        action_kind="OPPORTUNITY_SKIP",
        damage_dealt=0.0,
        kills_dealt=0,
        objective_had_opportunity=True,
        objective_progress_delta=0.0,
        objective_distance_before=1.0,
        legal_capture_options=1,
        reward_shaping={
            "opportunity_skip_capture_preserve_bonus": 0.07,
            "opportunity_vp_distance_threshold": 2.0,
            "idle_penalty": 0.0,
        },
    )
    assert fire_comp["opportunity_fire_no_progress"] == 0.0
    assert skip_comp["opportunity_skip_capture_preserve"] == 0.0
    assert fire_total > skip_total
