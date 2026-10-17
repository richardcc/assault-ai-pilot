import math
import pytest
import yaml

from assault_bench.runner import _resolve_enabled_profiles, _run_episode_with_policy, run_benchmark
from agents.muzero.adapter_voec import MuZeroVOECAdapter
from agents.muzero.core.mcts import MCTSOutput
from voec_sim.core.simulator import VOECSimulator


def test_benchmark_returns_results():
    payload = run_benchmark(config_path="assault_bench/configs/benchmark_config.test.yaml")
    assert "results" in payload
    assert len(payload["results"]) >= 2
    assert "terminal_reasons" in payload["results"][0]
    assert "phase_2_9_train_eval" in payload
    assert "phase_2_9_promotion_gate" in payload
    muzero_row = next(r for r in payload["results"] if r["agent_name"] == "muzero_stub")
    assert "phase_2_9_eval_kpis" in muzero_row
    assert "reaction_fire_count" in muzero_row["phase_2_9_eval_kpis"]
    steps_top = list(muzero_row.get("eval_decision_steps_top", []) or [])
    if steps_top:
        top = dict(steps_top[0] or {})
        for key in (
            "unit_prefilter_enabled",
            "unit_prefilter_selected_unit_id",
            "unit_prefilter_constrained_count",
            "unit_prefilter_global_count",
        ):
            assert key in top


def test_eval_trace_rows_include_head_telemetry_coverage():
    adapter = MuZeroVOECAdapter(VOECSimulator())
    _, _, _, _, _, _, _, _, _, _, _, _, trace_rows = _run_episode_with_policy(
        adapter=adapter,
        scenario_id="battaglia_cittadina_2_1",
        seed=7,
        policy_name="random",
        policy_by_side={},
        max_steps=6,
        max_steps_override=6,
        mcts_simulations=8,
        mcts_c_puct=1.5,
        mcts_temperature=1.0,
        model=None,
        action_dim=32,
        mcts_unroll_steps=1,
        mcts_discount=0.997,
        collect_flow_metrics=True,
    )
    assert isinstance(trace_rows, list)
    assert len(trace_rows) > 0
    row = dict(trace_rows[0] or {})
    assert row.get("telemetry_schema_version") == "head_telemetry_v1"
    assert row.get("telemetry_coverage_status") in {"none", "partial", "complete"}
    assert "telemetry_coverage_reason" in row
    heads = dict(row.get("telemetry_heads", {}) or {})
    for head_name in ("policy", "value", "reward", "objective", "consistency", "mcts"):
        assert head_name in heads
        assert str(dict(heads.get(head_name, {}) or {}).get("status", "")) != ""
    assert "objective_min_dist_before" in row
    assert "objective_min_dist_after" in row
    assert "objective_best_vp_id" in row
    assert "vp_distance_vector" in row
    assert "vp_distance_vector_size" in row
    assert "objective_signal_definition_version" in row
    assert isinstance(row.get("legal_actions", None), list)
    assert len(list(row.get("legal_actions", []) or [])) >= 1
    assert isinstance(row.get("legal_actions_decoded_target_qr", None), list)
    assert isinstance(row.get("acting_unit_action_catalog", None), list)
    assert any(
        str(item.get("action_id", "")) == str(row.get("action_id", ""))
        for item in list(row.get("legal_actions_decoded_target_qr", []) or [])
    )
    assert all("catalog_index" in dict(item or {}) for item in list(row.get("acting_unit_action_catalog", []) or []))


def test_eval_objective_head_not_partial_when_distance_present():
    adapter = MuZeroVOECAdapter(VOECSimulator())
    _, _, _, _, _, _, _, _, _, _, _, _, trace_rows = _run_episode_with_policy(
        adapter=adapter,
        scenario_id="battaglia_cittadina_2_1",
        seed=11,
        policy_name="random",
        policy_by_side={},
        max_steps=8,
        max_steps_override=8,
        mcts_simulations=8,
        mcts_c_puct=1.5,
        mcts_temperature=1.0,
        model=None,
        action_dim=32,
        mcts_unroll_steps=1,
        mcts_discount=0.997,
        collect_flow_metrics=True,
    )
    assert trace_rows
    row_with_distance = next((dict(r or {}) for r in trace_rows if float(dict(r or {}).get("objective_min_dist_before", -1.0)) >= 0.0), None)
    assert row_with_distance is not None
    objective_head = dict((dict(row_with_distance.get("telemetry_heads", {}) or {})).get("objective", {}) or {})
    assert objective_head.get("status") == "complete"
    assert str(objective_head.get("reason", "")) != "objective_distance_not_in_eval_pipeline"


def test_eval_trace_rows_include_override_sanity_fields():
    adapter = MuZeroVOECAdapter(VOECSimulator())
    _, _, _, _, _, _, _, _, _, _, _, _, trace_rows = _run_episode_with_policy(
        adapter=adapter,
        scenario_id="battaglia_cittadina_2_1",
        seed=13,
        policy_name="random",
        policy_by_side={},
        max_steps=6,
        max_steps_override=6,
        mcts_simulations=8,
        mcts_c_puct=1.5,
        mcts_temperature=1.0,
        model=None,
        action_dim=32,
        mcts_unroll_steps=1,
        mcts_discount=0.997,
        collect_flow_metrics=True,
    )
    assert trace_rows
    row = dict(trace_rows[0] or {})
    assert "mcts_chosen_action" in row
    assert "policy_top_action" in row
    assert "policy_overridden_by_mcts" in row
    assert "override_sanity_consistent" in row


def test_eval_trace_rows_entropy_uses_visit_distribution_and_sets_collapse_label(monkeypatch):
    adapter = MuZeroVOECAdapter(VOECSimulator())

    def _fake_mcts(**kwargs):
        legal_actions = list(kwargs.get("legal_actions", []) or [])
        n = len(legal_actions)
        visits = [3, 2] + ([0] * max(0, n - 2))
        probs = [1.0] + ([0.0] * max(0, n - 1))
        return MCTSOutput(
            actions=list(legal_actions),
            visits=list(visits[:n]),
            probs=list(probs[:n]),
            chosen_action=str(legal_actions[0]) if legal_actions else "",
        )

    monkeypatch.setattr("assault_bench.runner.run_mcts_puct", _fake_mcts)
    monkeypatch.setattr("assault_bench.runner.run_mcts_puct_muzero", _fake_mcts)
    monkeypatch.setattr("assault_bench.runner.run_mcts_puct_ezv2", _fake_mcts)
    monkeypatch.setattr("assault_bench.episode_runner_impl.run_mcts_puct_muzero", _fake_mcts)
    monkeypatch.setattr("assault_bench.episode_runner_impl.run_mcts_puct_ezv2", _fake_mcts)

    _, _, _, _, _, _, _, _, _, _, _, _, trace_rows = _run_episode_with_policy(
        adapter=adapter,
        scenario_id="battaglia_cittadina_2_1",
        seed=17,
        policy_name="muzero_stub",
        policy_by_side={},
        max_steps=1,
        max_steps_override=1,
        mcts_simulations=8,
        mcts_c_puct=1.5,
        mcts_temperature=0.1,
        model=None,
        action_dim=32,
        mcts_unroll_steps=1,
        mcts_discount=0.997,
        collect_flow_metrics=True,
    )
    assert trace_rows
    row = dict(trace_rows[0] or {})
    expected_entropy = -((3.0 / 5.0) * math.log(3.0 / 5.0) + (2.0 / 5.0) * math.log(2.0 / 5.0))
    assert float(row.get("mcts_entropy", 0.0)) == pytest.approx(expected_entropy, rel=1e-6, abs=1e-8)
    assert row.get("mcts_entropy_source") == "root_visit_distribution"
    assert bool(row.get("mcts_entropy_collapse", False)) is False
    assert row.get("mcts_entropy_collapse_label") == "ok"


def test_default_benchmark_config_is_not_quick_profile():
    cfg = yaml.safe_load(open("assault_bench/configs/benchmark_config.yaml", "r", encoding="utf-8").read())
    bench = dict(cfg.get("benchmark", {}) or {})
    seeds = list(bench.get("seeds", []) or [])
    profiles = list(
        bench.get(
            "matchup_profiles",
            ["muzero_selfplay", "muzero_vs_random_side_a", "muzero_vs_random_side_b"],
        )
        or []
    )
    assert len(seeds) >= 5
    assert "random_selfplay" not in profiles
    assert len(seeds) * max(1, len(profiles)) >= 75


def test_matchup_profile_defaults_exclude_random_selfplay():
    defaults = _resolve_enabled_profiles({})
    assert "random_selfplay" not in defaults
    assert defaults == {"muzero_selfplay", "muzero_vs_random_side_a", "muzero_vs_random_side_b"}


def test_matchup_profile_allows_explicit_random_selfplay_opt_in():
    enabled = _resolve_enabled_profiles({"matchup_profiles": ["muzero_selfplay", "random_selfplay"]})
    assert enabled == {"muzero_selfplay", "random_selfplay"}
