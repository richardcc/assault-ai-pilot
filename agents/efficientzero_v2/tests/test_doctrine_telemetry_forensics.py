import pytest
from pathlib import Path
from agents.efficientzero_v2.core.macro_planner import MacroStrategyPlanner, MacroPlan
from assault_bench.unit_state_utils import unit_snapshot_dict
from assault_bench.episode_runner_impl import _decorate_units_with_macro_plan


def test_macro_strategy_planner_compute_action_boost():
    planner = MacroStrategyPlanner()
    plan = MacroPlan(
        posture="ASSAULT_VP",
        target_vp_id="vp1",
        target_vp_coords=(3, 3),
        unit_roles={"u1": "ROLE_FIRE_SUPPORT", "u2": "ROLE_SPEARHEAD"},
        unit_cohesion={"u1": "COHESIVE", "u2": "COHESIVE"},
        unit_coords={"u1": (1, 1), "u2": (2, 2)},
        unit_mutation_reasons={"u1": "DEFAULT_PROFILE", "u2": "DEFAULT_PROFILE"},
        unit_base_roles={"u1": "ROLE_FIRE_SUPPORT", "u2": "ROLE_SPEARHEAD"},
        unit_mutated={"u1": False, "u2": False},
        friendly_vp_count=0,
        enemy_vp_count=1,
        neutral_vp_count=1,
    )

    # Attack action for FIRE_SUPPORT -> boost 1.35
    boost_fs_atk = planner.compute_action_boost("ATTACK:u1:target_enemy", plan, {}, "US")
    assert boost_fs_atk == pytest.approx(1.35)

    # Move action for FIRE_SUPPORT -> boost 1.0 (neutral)
    boost_fs_move = planner.compute_action_boost("MOVE:u1:1,2", plan, {}, "US")
    assert boost_fs_move == pytest.approx(1.0)

    # Move closer to target VP for SPEARHEAD -> assault_boost * 1.25 = 1.35 * 1.25 = 1.6875
    boost_sh_move = planner.compute_action_boost("MOVE:u2:3,2", plan, {}, "US")
    assert boost_sh_move == pytest.approx(1.35 * 1.25)


def test_unit_snapshot_dict_doctrine_fields():
    raw_unit = {
        "unit_id": "us_hmg_1",
        "unit_key": "us_hmg_m2hb",
        "unit_label": "US HMG .50 M2HB Team",
        "side": "US",
        "q": 2,
        "r": 3,
        "hp": 4.0,
        "alive": True,
        "suppressed": False,
        "doctrine_role": "FIRE_SUPPORT",
        "active_role": "ROLE_FIRE_SUPPORT",
        "role_is_mutated": True,
        "role_mutation_reason": "FLANKED_CLOSE_DEFENSE",
        "prior_boost_applied": 0.35,
        "badge_label": "FIRE_SUPPORT",
    }

    snap = unit_snapshot_dict(raw_unit)
    assert snap["unit_id"] == "us_hmg_1"
    assert snap["doctrine_role"] == "FIRE_SUPPORT"
    assert snap["role_assigned"] == "ROLE_FIRE_SUPPORT"
    assert snap["role_is_mutated"] is True
    assert snap["role_mutation_reason"] == "FLANKED_CLOSE_DEFENSE"
    assert snap["prior_boost_applied"] == pytest.approx(0.35)
    assert snap["badge_label"] == "FIRE_SUPPORT"


def test_decorate_units_with_macro_plan():
    plan = MacroPlan(
        posture="ASSAULT_VP",
        target_vp_id="vp1",
        target_vp_coords=(3, 3),
        unit_roles={"us_inf_1": "ROLE_SPEARHEAD", "us_hmg_1": "ROLE_FIRE_SUPPORT"},
        unit_cohesion={"us_inf_1": "COHESIVE", "us_hmg_1": "COHESIVE"},
        unit_coords={"us_inf_1": (2, 2), "us_hmg_1": (1, 1)},
        unit_mutation_reasons={"us_inf_1": "VP_DEFICIT_PRESSURE", "us_hmg_1": "DEFAULT_PROFILE"},
        unit_base_roles={"us_inf_1": "ROLE_SPEARHEAD", "us_hmg_1": "ROLE_FIRE_SUPPORT"},
        unit_mutated={"us_inf_1": True, "us_hmg_1": False},
        friendly_vp_count=0,
        enemy_vp_count=1,
        neutral_vp_count=1,
    )

    raw_units = [
        {"unit_id": "us_inf_1", "side": "US", "hp": 4.0, "alive": True},
        {"unit_id": "us_hmg_1", "side": "US", "hp": 3.0, "alive": True},
    ]

    decorated = _decorate_units_with_macro_plan(
        raw_units,
        plan,
        acting_unit_id="us_inf_1",
        prior_boost=0.35,
    )

    inf = next(u for u in decorated if u["unit_id"] == "us_inf_1")
    assert inf["role_assigned"] == "ROLE_SPEARHEAD"
    assert inf["role_is_mutated"] is True
    assert inf["role_mutation_reason"] == "VP_DEFICIT_PRESSURE"
    assert inf["prior_boost_applied"] == pytest.approx(0.35)
    assert inf["badge_label"] == "SPEARHEAD"

    hmg = next(u for u in decorated if u["unit_id"] == "us_hmg_1")
    assert hmg["role_assigned"] == "ROLE_FIRE_SUPPORT"
    assert hmg["role_is_mutated"] is False
    assert hmg["role_mutation_reason"] == "DEFAULT_PROFILE"
    assert hmg["prior_boost_applied"] == pytest.approx(0.0)
    assert hmg["badge_label"] == "FIRE_SUPPORT"


def test_timeline_exporter_preserves_doctrine_fields(tmp_path: Path):
    from agents.efficientzero_v2.xai.timeline_exporter import export_muzero_episode_timeline
    import json

    run_id = "ezv2_test_doctrine"
    run_dir = tmp_path / "runs" / run_id
    events_dir = run_dir / "events"
    events_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "run_manifest.json").write_text(
        json.dumps({"scenario_id": "battaglia_cittadina_2_1", "seed": 42}),
        encoding="utf-8",
    )

    payload = {
        "type": "TransitionEvent",
        "payload": {
            "iteration": 0,
            "episode": 0,
            "step": 0,
            "game_turn": 1,
            "to_play": "US",
            "action_id": "ATTACK:us_hmg_1:it_rifles_1",
            "action_kind": "ATTACK",
            "unit_id": "us_hmg_1",
            "unit_side": "US",
            "unit_label": "US HMG .50 M2HB Team",
            "role_assigned": "ROLE_FIRE_SUPPORT",
            "role_is_mutated": False,
            "role_mutation_reason": "DEFAULT_PROFILE",
            "prior_boost_applied": 0.35,
            "badge_label": "FIRE_SUPPORT",
            "reward_target": 0.5,
            "done": False,
            "units_snapshot": [
                {
                    "unit_id": "us_hmg_1",
                    "side": "US",
                    "role_assigned": "ROLE_FIRE_SUPPORT",
                    "role_is_mutated": False,
                    "role_mutation_reason": "DEFAULT_PROFILE",
                    "prior_boost_applied": 0.35,
                    "badge_label": "FIRE_SUPPORT",
                }
            ],
            "transition_info": {},
        },
    }

    (events_dir / "train_events.jsonl").write_text(
        json.dumps(payload) + "\n",
        encoding="utf-8",
    )

    timeline = export_muzero_episode_timeline(tmp_path, run_id, iteration=0, episode=0)
    assert len(timeline["transitions"]) == 1
    tr = timeline["transitions"][0]
    assert tr["role_assigned"] == "ROLE_FIRE_SUPPORT"
    assert tr["role_is_mutated"] is False
    assert tr["role_mutation_reason"] == "DEFAULT_PROFILE"
    assert tr["prior_boost_applied"] == pytest.approx(0.35)
    assert tr["badge_label"] == "FIRE_SUPPORT"

    u = tr["units"][0]
    assert u["role_assigned"] == "ROLE_FIRE_SUPPORT"
    assert u["role_is_mutated"] is False
    assert u["prior_boost_applied"] == pytest.approx(0.35)

