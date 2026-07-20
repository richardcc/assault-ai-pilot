from types import SimpleNamespace

import torch

from agents.efficientzero_v2.core.interop import load_efficientzero_config
from agents.efficientzero_v2.core.network import EfficientZeroV2Network
from agents.efficientzero_v2.core.replay import ReplaySample
from agents.efficientzero_v2.train.trainer import EfficientZeroV2Trainer
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


def test_episode_phase29_counts_melee_damage_success_from_assault_steps() -> None:
    samples = [
        SimpleNamespace(
            info={
                "action_kind": "ASSAULT_MELEE",
                "damage_dealt": 4.0,
                "kills_dealt": 1,
            }
        ),
        SimpleNamespace(
            info={
                "action_kind": "ASSAULT_MELEE",
                "damage_dealt": 0.0,
                "kills_dealt": 0,
            }
        ),
    ]
    out = _episode_phase29_from_samples(samples)
    assert out["melee_attempts"] == 2.0
    assert out["melee_damage_sum"] == 4.0
    assert out["melee_success_count"] == 1.0
    assert out["melee_kills_sum"] == 1.0


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


def test_ezv2_loader_defaults_include_vp_tuning_and_aux_keys(tmp_path) -> None:
    cfg_path = tmp_path / "cfg.yaml"
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
                "selfplay: {}",
                "train: {}",
            ]
        ),
        encoding="utf-8",
    )
    cfg = load_efficientzero_config(cfg_path)
    assert float(cfg.selfplay["reward_shaping"]["objective_progress_bonus_per_hex"]) == 0.95
    assert float(cfg.train["objective_pos_weight"]) == 6.8
    assert "aux_objective_enabled" in cfg.train
    assert "aux_multi_vp_feature_dim" in cfg.train


def test_trainer_aux_objective_wiring_smoke_contract() -> None:
    model = EfficientZeroV2Network(
        observation_dim=4,
        hidden_dim=16,
        action_dim=8,
        encoder_type="mlp",
        objective_intent_classes=4,
        multi_vp_feature_dim=3,
    )
    trainer = EfficientZeroV2Trainer(
        model=model,
        lr=1e-3,
        device="cpu",
        objective_loss_weight=0.0,
        aux_objective_enabled=True,
        aux_objective_loss_weight=1.0,
        aux_intent_loss_weight=0.5,
        aux_multi_vp_loss_weight=0.5,
        aux_multi_vp_feature_dim=3,
    )
    sample = ReplaySample(
        observation=torch.tensor([1.0, 0.0, 0.0, 0.0], dtype=torch.float32),
        policy_target=[1.0] + [0.0] * 7,
        value_target=0.0,
        reward_target=0.0,
        info={
            "objective_had_opportunity": 1,
            "objective_progress_delta": 1.0,
            "objective_converted": 0,
            "vp_distance_vector": {"VP_1": 1.0, "VP_2": 2.0, "VP_3": 3.0},
        },
    )
    metrics = trainer.train_batch([sample])
    md = metrics.to_dict()
    assert "aux_objective_loss" in md
    assert "aux_intent_loss" in md
    assert "aux_multi_vp_loss" in md
