"""Unit tests for the evolutionary curriculum cycle optimizer."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from agents.efficientzero_v2.curriculum.evolutionary_cycle_optimizer import (
    analyze_and_evolve_curriculum,
    audit_last_curriculum_run,
    evolve_phase_cycles,
    synthesize_adaptive_cycle_overlays,
)


@pytest.fixture
def mock_curriculum_env(tmp_path: Path):
    """Creates a temporary curriculum workspace for testing."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    curr_dir = repo_root / "curriculums" / "test_curriculum"
    configs_dir = curr_dir / "configs"
    cycles_dir = curr_dir / "cycles"
    reporting_dir = repo_root / "runs_curriculum" / "experiments" / "reporting"

    configs_dir.mkdir(parents=True)
    cycles_dir.mkdir(parents=True)
    reporting_dir.mkdir(parents=True)

    # Base config for phase 1
    phase1_cfg = {
        "base_config": "agents/efficientzero_v2/configs/efficientzero_v2_config.yaml",
        "selfplay": {
            "mcts_temperature": 1.10,
            "reward_shaping": {
                "vp_capture_bonus_per_hex": 2.50,
                "objective_progress_bonus_per_hex": 1.80,
                "capture_bonus": 1.00,
                "vp_potential_weight": 1.00,
            },
        },
        "train": {
            "reanalysis_ratio": 0.35,
            "train_updates_per_iter": 10,
            "objective_loss_weight": 0.20,
            "resume_checkpoint": "/tmp/dummy.pt",  # Should be stripped
        },
    }
    phase1_cfg_path = configs_dir / "phase1.yaml"
    phase1_cfg_path.write_text(yaml.safe_dump(phase1_cfg), encoding="utf-8")

    # Curriculum YAML
    curr_yaml_data = {
        "name": "test_curriculum_v1",
        "phases": [
            {
                "name": "phase1_test",
                "train_config": "curriculums/test_curriculum/configs/phase1.yaml",
            }
        ],
    }
    curr_yaml_path = curr_dir / "curriculum.yaml"
    curr_yaml_path.write_text(yaml.safe_dump(curr_yaml_data), encoding="utf-8")

    # Traceability JSONL with 3 cycles (Cycle 3 is winner)
    trace_path = reporting_dir / "curriculum_phase_traceability.jsonl"
    rows = [
        {
            "curriculum_name": "test_curriculum_v1",
            "phase_name": "phase1_test",
            "cycle_iteration": 1,
            "promotion_decision": "hold",
            "tactical_quality_score": 0.50,
            "gate_metrics": {"resolved_non_timeout_win_rate": 0.50},
        },
        {
            "curriculum_name": "test_curriculum_v1",
            "phase_name": "phase1_test",
            "cycle_iteration": 2,
            "promotion_decision": "hold",
            "tactical_quality_score": 0.55,
            "gate_metrics": {"resolved_non_timeout_win_rate": 0.55},
        },
        {
            "curriculum_name": "test_curriculum_v1",
            "phase_name": "phase1_test",
            "cycle_iteration": 3,
            "promotion_decision": "promote",
            "tactical_quality_score": 0.85,
            "gate_metrics": {"resolved_non_timeout_win_rate": 0.85},
        },
    ]
    with trace_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    return {
        "repo_root": repo_root,
        "curr_yaml_path": curr_yaml_path,
        "phase1_cfg_path": phase1_cfg_path,
        "trace_path": trace_path,
        "cycles_dir": cycles_dir,
    }


def test_audit_last_curriculum_run(mock_curriculum_env):
    repo_root = mock_curriculum_env["repo_root"]
    trace_path = mock_curriculum_env["trace_path"]

    audits = audit_last_curriculum_run(repo_root=repo_root, curriculum_name="test_curriculum_v1", trace_path=trace_path)
    assert len(audits) == 1
    res = audits[0]
    assert res["phase_name"] == "phase1_test"
    assert res["winning_cycle"] == 3
    assert res["promotion_decision"] == "promote"
    assert res["win_rate"] == 0.85


def test_synthesize_adaptive_cycle_overlays():
    base_cfg = {
        "selfplay": {
            "mcts_temperature": 1.10,
            "reward_shaping": {
                "vp_capture_bonus_per_hex": 2.50,
                "objective_progress_bonus_per_hex": 1.80,
                "capture_bonus": 1.00,
                "vp_potential_weight": 1.00,
            },
        },
        "train": {
            "reanalysis_ratio": 0.35,
            "train_updates_per_iter": 10,
            "objective_loss_weight": 0.20,
        },
    }

    overlays = synthesize_adaptive_cycle_overlays(base_config=base_cfg, generation=2, winning_cycle=3)
    assert 1 in overlays
    assert 2 in overlays
    assert 3 in overlays

    # C1 is baseline
    assert overlays[1]["strategy"] == "promoted_baseline"

    # C2 is exploitation
    c2 = overlays[2]["overlay"]
    assert c2["train"]["reanalysis_ratio"] == 0.40  # 0.35 + 0.05
    assert c2["train"]["train_updates_per_iter"] == 12  # 10 + 2
    assert c2["selfplay"]["mcts_temperature"] == 1.05  # 1.10 - 0.05

    # C3 is exploration
    c3 = overlays[3]["overlay"]
    assert c3["train"]["objective_loss_weight"] == 0.25  # 0.20 + 0.05
    assert c3["train"]["train_updates_per_iter"] == 14  # 10 + 4
    assert c3["selfplay"]["reward_shaping"]["vp_capture_bonus_per_hex"] == pytest.approx(2.50 * 1.15, 0.01)


def test_evolve_phase_cycles_strips_checkpoints(mock_curriculum_env):
    repo_root = mock_curriculum_env["repo_root"]
    phase1_cfg_path = mock_curriculum_env["phase1_cfg_path"]

    winning_info = {
        "curriculum_name": "test_curriculum_v1",
        "phase_name": "phase1_test",
        "winning_cycle": 3,
        "win_rate": 0.85,
        "tactical_quality_score": 0.85,
        "promotion_decision": "promote",
    }

    res = evolve_phase_cycles(
        repo_root=repo_root,
        phase_name="phase1_test",
        base_config_path=phase1_cfg_path,
        winning_cycle_info=winning_info,
    )

    assert res["ok"] is True
    assert res["generation"] == 2
    assert res["winning_cycle"] == 3

    # Check updated base config: resume_checkpoint must be absent
    updated_cfg = yaml.safe_load(phase1_cfg_path.read_text(encoding="utf-8"))
    assert "resume_checkpoint" not in updated_cfg.get("train", {})

    # Check adaptive cycle plan YAML
    plan_path = Path(res["plan_path"])
    assert plan_path.exists()
    plan_data = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
    assert plan_data["generation"] == 2
    assert plan_data["winning_history"][0]["winning_cycle"] == 3
    assert 1 in plan_data["cycles"]
    assert 2 in plan_data["cycles"]
    assert 3 in plan_data["cycles"]


def test_analyze_and_evolve_curriculum_e2e(mock_curriculum_env):
    repo_root = mock_curriculum_env["repo_root"]
    curr_yaml_path = mock_curriculum_env["curr_yaml_path"]

    res = analyze_and_evolve_curriculum(repo_root=repo_root, curriculum_yaml=curr_yaml_path)
    assert res["ok"] is True
    assert res["curriculum_name"] == "test_curriculum_v1"
    assert len(res["evolved_phases"]) == 1

    ev_phase = res["evolved_phases"][0]
    assert ev_phase["phase_name"] == "phase1_test"
    assert ev_phase["generation"] == 2
    assert ev_phase["winning_cycle"] == 3
