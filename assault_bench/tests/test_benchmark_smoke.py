import yaml

from assault_bench.runner import _run_episode_with_policy, run_benchmark
from agents.muzero.adapter_voec import MuZeroVOECAdapter
from voec_sim.configs.config_loader import load_voec_config
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


def test_eval_trace_rows_include_head_telemetry_coverage():
    adapter = MuZeroVOECAdapter(VOECSimulator(config=load_voec_config("assault_sim/config/train_config.json")))
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


def test_eval_objective_head_not_partial_when_distance_present():
    adapter = MuZeroVOECAdapter(VOECSimulator(config=load_voec_config("assault_sim/config/train_config.json")))
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
    adapter = MuZeroVOECAdapter(VOECSimulator(config=load_voec_config("assault_sim/config/train_config.json")))
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


def test_default_benchmark_config_is_not_quick_profile():
    cfg = yaml.safe_load(open("assault_bench/configs/benchmark_config.yaml", "r", encoding="utf-8").read())
    bench = dict(cfg.get("benchmark", {}) or {})
    seeds = list(bench.get("seeds", []) or [])
    profiles = list(
        bench.get(
            "matchup_profiles",
            ["muzero_selfplay", "random_selfplay", "muzero_vs_random_side_a", "muzero_vs_random_side_b"],
        )
        or []
    )
    assert len(seeds) >= 5
    assert len(seeds) * max(1, len(profiles)) >= 100
