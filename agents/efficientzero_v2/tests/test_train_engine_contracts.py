from types import SimpleNamespace

from agents.efficientzero_v2.train.train_engine import (
    _collect_config_preflight_warnings,
    _build_units_sides_contract,
    _episode_phase29_from_samples,
    _episode_length_diagnostics,
)


def test_episode_length_diagnostics_tracks_short_rate_and_buckets() -> None:
    rows = [
        {"length": 42, "outcome_bucket": "loss", "reason": "turn_unit_budget"},
        {"length": 110, "outcome_bucket": "win", "reason": "scenario_end"},
        {"length": 65, "outcome_bucket": "loss", "reason": "turn_unit_budget"},
    ]
    diag = _episode_length_diagnostics(rows=rows, threshold=80)
    assert diag["episodes"] == 3
    assert diag["short_episode_rate"] == 2.0 / 3.0
    assert diag["length_p50"] == 65.0
    assert "loss" in diag["short_by_outcome"]
    assert "turn_unit_budget" in diag["short_by_reason"]


def test_build_units_sides_contract_emits_required_fields() -> None:
    samples = [
        SimpleNamespace(
            info={
                "unit_side": "A",
                "unit_id": "u1",
                "action_kind": "CAPTURE",
                "vp_captures": 1,
                "objective_outcome_bucket_actor": "win",
                "terminal_reason": "scenario_end",
            }
        ),
        SimpleNamespace(
            info={
                "unit_side": "B",
                "unit_id": "u2",
                "action_kind": "RANGED",
                "vp_captures": 0,
                "objective_outcome_bucket_actor": "loss",
                "timeout": True,
            }
        ),
    ]
    payload = _build_units_sides_contract(
        samples=samples,
        latest_metrics={"phase_2_9_train_kpis": {"reaction_fire_count": 1.0}},
        scenario_id="s1",
        run_id="efficientzero_v2_test",
    )
    for key in (
        "transition_events",
        "side_turn_counts",
        "side_turn_rates",
        "top_action_units",
        "units_by_side",
        "global_actions",
        "vp_summary",
        "strategy_summary",
    ):
        assert key in payload
    assert payload["engine"] == "efficientzero_v2"


def test_episode_phase29_respects_conversion_window_override() -> None:
    samples = [
        SimpleNamespace(info={"objective_progress_delta": 1.0, "objective_converted": 0}),
        SimpleNamespace(info={"objective_progress_delta": 0.0, "objective_converted": 0}),
        SimpleNamespace(info={"objective_progress_delta": 0.0, "objective_converted": 1}),
    ]
    base = _episode_phase29_from_samples(samples, conversion_window_steps=2)
    strict = _episode_phase29_from_samples(samples, conversion_window_steps=1)
    assert base["conversion_within_2_after_progress"] == 1.0
    assert strict["conversion_within_2_after_progress"] == 0.0


def test_config_preflight_warns_when_critical_blocks_missing(tmp_path) -> None:
    cfg_path = tmp_path / "legacy_missing.yaml"
    cfg_path.write_text(
        "\n".join(
            [
                "paths:",
                "  run_root: runs",
                "scenario:",
                "  id: s1",
                "  seed: 1",
                "model:",
                "  observation_dim: 4",
                "selfplay:",
                "  max_steps: 10",
                "train:",
                "  iterations: 1",
            ]
        ),
        encoding="utf-8",
    )
    warnings = _collect_config_preflight_warnings(cfg_path)
    assert "missing.selfplay.reward_shaping" in warnings
    assert "missing.train.objective_signal" in warnings
    assert "missing.train.objective_head" in warnings
    assert "missing.train.objective_reporting" in warnings
