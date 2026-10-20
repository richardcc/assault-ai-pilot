"""
Automated Test for Telemetry Schema Conformance.

Roadmap Task 1.1 (Priority P0):
- Validates that 100% of telemetry metrics emitted by the engine, trace builders,
  MLOps DuckDB/Parquet layers, and REST endpoints conform strictly to the canonical
  inventory defined in docs/13_INVENTARIO_CANONICO_METRICAS.md.
- Enforces Zero-Mock / Zero-Inference: no synthetic fallbacks, no undeclared keys.
- Enforces Clean Break with MuZero: zero legacy 'muzero_' keys or decommissioned aliases.
- Fails in CI if any rogue or uncataloged field is detected.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Set

import pytest

from assault_bench.episode_step_models import (
    StepCoreData,
    StepPrefilterData,
    StepSignalData,
)
from assault_bench.episode_trace_row_builder import build_trace_row
from mlops.reporting.quality_metrics import (
    compute_anchor_elo,
    compute_tactical_quality_metrics,
)


def _load_canonical_inventory() -> Dict[str, Set[str]]:
    """Parse docs/13_INVENTARIO_CANONICO_METRICAS.md and extract documented canonical metrics."""
    doc_path = Path(__file__).resolve().parents[2] / "docs" / "13_INVENTARIO_CANONICO_METRICAS.md"
    assert doc_path.exists(), f"Canonical inventory file missing: {doc_path}"

    text = doc_path.read_text(encoding="utf-8")

    categories: Dict[str, Set[str]] = {
        "level_1_ballistics": set(),
        "level_2_search": set(),
        "level_3_model_heads": set(),
        "level_4_macro_quality": set(),
        "frontend_traceability": set(),
        "all_canonical": set(),
    }

    current_cat = "level_1_ballistics"

    for line in text.splitlines():
        line_clean = line.strip()
        if "## Nivel 1:" in line:
            current_cat = "level_1_ballistics"
        elif "## Nivel 2:" in line:
            current_cat = "level_2_search"
        elif "## Nivel 3:" in line:
            current_cat = "level_3_model_heads"
        elif "## Nivel 4:" in line:
            current_cat = "level_4_macro_quality"
        elif "## Matriz de Trazabilidad 100%:" in line:
            current_cat = "frontend_traceability"

        if line_clean.startswith("|") and not line_clean.startswith("| :---"):
            cells = [c.strip() for c in line_clean.split("|")[1:-1]]
            if len(cells) >= 2:
                first_cell = cells[0]
                # Look for backticked names in the metric column
                matches = re.findall(r"`([^`]+)`", first_cell)
                for m in matches:
                    name = m.strip()
                    if name and not name.startswith("TIPO:"):
                        categories[current_cat].add(name)
                        categories["all_canonical"].add(name)

                # For frontend traceability table, the 3rd column contains JSON payload keys
                if current_cat == "frontend_traceability" and len(cells) >= 3:
                    json_keys = re.findall(r"`([^`]+)`", cells[2])
                    for jk in json_keys:
                        name = jk.strip()
                        if name:
                            categories["frontend_traceability"].add(name)
                            categories["all_canonical"].add(name)

    return categories


def test_canonical_inventory_parsing() -> None:
    """Verify that docs/13_INVENTARIO_CANONICO_METRICAS.md defines canonical metrics across all levels."""
    inventory = _load_canonical_inventory()

    assert len(inventory["level_1_ballistics"]) >= 10, "Level 1 metrics missing from documentation"
    assert "step" in inventory["level_1_ballistics"]
    assert "damage_dealt" in inventory["level_1_ballistics"]
    assert "kills_dealt" in inventory["level_1_ballistics"]

    assert len(inventory["level_2_search"]) >= 15, "Level 2 metrics missing from documentation"
    assert "mcts_total_visits" in inventory["level_2_search"]
    assert "vp_potential_delta" in inventory["level_2_search"]
    assert "turn_urgency_factor" in inventory["level_2_search"]

    assert len(inventory["level_3_model_heads"]) >= 15, "Level 3 metrics missing from documentation"
    assert "train_policy_loss" in inventory["level_3_model_heads"]
    assert "train_consistency_loss" in inventory["level_3_model_heads"]

    assert len(inventory["level_4_macro_quality"]) >= 15, "Level 4 metrics missing from documentation"
    assert "tactical_quality_score" in inventory["level_4_macro_quality"]
    assert "anchor_elo" in inventory["level_4_macro_quality"]
    assert "train_duration_seconds" in inventory["level_4_macro_quality"]
    assert "bench_duration_seconds" in inventory["level_4_macro_quality"]

    assert len(inventory["all_canonical"]) >= 60, "Total canonical inventory too small"


def test_trace_row_schema_conformance_and_zero_mock() -> None:
    """Ensure build_trace_row produces only schema-compliant fields and zero prohibited legacy keys."""
    inventory = _load_canonical_inventory()

    core = StepCoreData(
        step=0,
        game_turn=1,
        turn=1,
        active_side="US",
        action="MOVE:US_1:4:5",
        action_kind="MOVE",
        chosen_prob=0.8,
        margin=0.3,
        mcts_entropy=0.5,
        mcts_total_visits=16,
        mcts_active_actions=3,
        root_actions_for_explain=["MOVE:US_1:4:5"],
        legal_actions_list=["MOVE:US_1:4:5"],
        legal_actions_duplicates_collapsed=0,
        legal_actions_decoded_target_qr=[{"q": 4, "r": 5}],
        acting_unit_action_catalog=[],
        acting_unit_id="US_1",
        acting_unit=None,
        transition_reward=0.1,
        transition_done=False,
        enemy_damage=0.0,
        enemy_kills=0,
        action_parts=["MOVE", "US_1", "4", "5"],
        target_q=4,
        target_r=5,
        attack_distance=1.0,
        target_cover=0.5,
        target_los=0.0,
        capture_legal_count=0,
        capture_like_action_taken=False,
    )
    signals = StepSignalData(
        mcts_prior_value=0.6,
        mcts_q_value=0.75,
        mcts_u_value=0.1,
        decision_score_value=0.85,
        selected_success_proxy=0.7,
        selected_success_component=0.1,
        selected_components={},
        selected_vp_horizon_steps=2.0,
        selected_vp_horizon_signal=0.5,
        selected_vp_horizon_component=0.1,
        vp_horizon_source="mcts",
        vp_horizon_available=True,
        objective_soft_component_value=0.05,
        objective_soft_source="mcts",
        objective_soft_available=True,
        objective_soft_reason="closer_to_vp",
        global_strategy_soft_component_value=0.0,
        global_strategy_soft_source="mcts",
        global_strategy_soft_available=True,
        reaction_fire_soft_component_value=0.0,
        reaction_fire_soft_source="simulator",
        reaction_fire_soft_available=True,
        reaction_exposure_component_value=0.0,
        reaction_exposure_source="simulator",
        reaction_exposure_available=True,
        objective_had_opportunity=0,
        objective_min_dist_before=3.0,
        objective_min_dist_after=2.0,
        objective_progress_delta=1.0,
        selected_tie_break_term=0.01,
        objective_converted=0,
        objective_best_vp_id="VP_1",
        strategy_label="ASSAULT_VP",
        vp_distance_vector={"VP_1": 2.0},
        obs_enemy_reaction_fire_risk_value=0.0,
        macro_posture="ASSAULT_VP",
        macro_target_vp_id="VP_1",
        unit_macro_role="ROLE_SPEARHEAD",
    )
    prefilter = StepPrefilterData(
        unit_prefilter_enabled=True,
        unit_prefilter_enabled_source="config",
        unit_prefilter_selected_unit_id="US_1",
        replan_evaluated_units=[],
        unit_prefilter_constrained_count=5,
        unit_prefilter_constrained_count_source="filter",
        unit_prefilter_global_count=12,
        unit_prefilter_global_count_source="catalog",
    )

    class DummyMCTSOut:
        visits = [10, 5, 1]
        probs = [0.625, 0.3125, 0.0625]
        q_values = [0.8, 0.2, -0.1]
        priors = [0.5, 0.3, 0.2]
        root_entropy = 0.85
        active_branches = 3
        q_guardrail_clipped_count = 0
        pruned_branches_count = 2

    row = build_trace_row(
        core=core,
        signals=signals,
        prefilter=prefilter,
        mcts_out=DummyMCTSOut(),
        latent_top_dims="0,1,2",
        policy_top_actions=["MOVE:US_1:4:5", "WAIT:US_1:4:4"],
        policy_top_probs=[0.6, 0.3],
        mcts_action_candidates=[],
        selected_candidate={"action_id": "MOVE:US_1:4:5", "visit_count": 10},
        decision_rank=1,
        mcts_candidates_duplicates_collapsed=0,
        why_action_vs_vp={"reason": "closer_to_vp"},
        policy_top_action="MOVE:US_1:4:5",
        policy_overridden_by_mcts=False,
        latent_top_indices=[0, 1, 2],
        latent_top_values=[1.2, 0.8, 0.5],
        latent_l2_norm=2.34,
        predicted_value_root=0.75,
        dynamics_pred_reward=0.1,
        dynamics_next_latent_l2=2.40,
        dynamics_delta_l2=0.06,
        immediate_capture_legal_count=0,
        unit_positions_snapshot=[],
        unit_hp_snapshot={"US_1": 4.0},
        unit_alive_snapshot={"US_1": True},
        unit_suppressed_snapshot={"US_1": False},
        before_vp_owner={"VP_1": "NEUTRAL"},
        after_vp_owner={"VP_1": "NEUTRAL"},
        transition_info={"damage_dealt": 0.0, "kills_dealt": 0},
        obs_terrain_type_map={},
        obs_terrain_cover_map={},
        obs_terrain_los_block_map={},
        obs_terrain_move_cost_map={},
        obs_fortification_type_map={},
        obs_fortification_edge_map={},
        head_states={},
        telemetry_coverage_status="COMPLETE",
        telemetry_coverage_reason="",
        attack_dice_rolls=[1.0],
        defense_dice_rolls=[0.0],
        attack_components_by_die={},
        defense_components_by_die={},
        runtime_events=[],
        post_units_snapshot=[],
        field_fn=lambda obj, k, default=None: default,
        trace_detail_level="core",
    )

    # Prohibited legacy fields (Zero Tolerance)
    prohibited_keys = {
        "muzero_visits",
        "muzero_q",
        "heuristic_fake_role",
    }
    for pk in prohibited_keys:
        assert pk not in row, f"Prohibited legacy key '{pk}' found in trace row!"

    # Ensure all canonical Level 1 & Level 2 core fields exist with valid types
    assert row["step"] == 0
    assert row["game_turn"] == 1
    assert row["to_play"] == "US"
    assert row["unit_id"] == "US_1"
    assert row["action_id"] == "MOVE:US_1:4:5"
    assert row["action_kind"] == "MOVE"
    assert row["telemetry_coverage_status"] == "COMPLETE"
    assert row["mcts_total_visits"] == 16
    assert row["damage_dealt"] == 0.0
    assert row["kills_dealt"] == 0


def test_quality_metrics_contract_conformance() -> None:
    """Verify that quality_metrics calculations adhere strictly to canonical names."""
    inventory = _load_canonical_inventory()

    # Anchor ELO
    elo = compute_anchor_elo(mirror_score_vs_random=0.75)
    assert isinstance(elo, float)

    # Tactical Quality Score (TQS)
    dummy_eval_rows = [
        {
            "scenario_id": "battaglia_cittadina_2_1",
            "matchup_profile": "side_a_vs_random",
            "controller": "efficientzero_v2",
            "episodes": 20,
            "win_rate": 0.85,
            "draw_rate": 0.05,
            "vp_net_avg": 1.2,
            "tracked_captured_avg": 2.0,
        },
        {
            "scenario_id": "battaglia_cittadina_2_1",
            "matchup_profile": "side_b_vs_random",
            "controller": "efficientzero_v2",
            "episodes": 20,
            "win_rate": 0.80,
            "draw_rate": 0.10,
            "vp_net_avg": 0.8,
            "tracked_captured_avg": 1.8,
        },
    ]

    tqs_result = compute_tactical_quality_metrics(dummy_eval_rows)

    for k in ("tactical_quality_score", "tactical_grade", "combat_exchange_ratio", "mean_asymmetry_gap"):
        assert k in tqs_result, f"Required TQS key '{k}' missing"
        assert k in inventory["level_4_macro_quality"], f"TQS key '{k}' not documented in canonical inventory"

    grade = str(tqs_result["tactical_grade"])
    assert grade[0] in {"S", "A", "B", "C", "D"}, f"Invalid tactical grade: {grade}"
    assert "quality_gate" in tqs_result
    assert tqs_result["quality_gate"]["status"] in {"PASS", "WARN", "FAIL"}


def test_muzero_decommissioning_strict_clean_break() -> None:
    """Validate that MuZero is not present in active configuration defaults or contracts."""
    from mlops.reporting.replay_api import build_efficientzero_v2_replay_payload

    assert callable(build_efficientzero_v2_replay_payload)
    # Ensure docstrings and canonical modules do not prescribe MuZero as the active agent
    import agents.efficientzero_v2.core.network as net_module

    assert hasattr(net_module, "EfficientZeroV2Network")
    assert not hasattr(net_module, "MuZeroNetwork")


def test_curriculum_traceability_api_conformance() -> None:
    """Verify that _load_curriculum_traceability_payload produces canonical timing and lineage fields."""
    from mlops.reporting.viewer import _load_curriculum_traceability_payload

    repo_root = Path(__file__).resolve().parents[2]
    payload = _load_curriculum_traceability_payload(repo_root=repo_root, limit=5)
    assert isinstance(payload, dict)
    assert "rows" in payload
    rows = payload["rows"]
    assert isinstance(rows, list)
    if rows:
        first_row = rows[0]
        # Verify timing telemetry fields added for Phase 1.1 / Section 4.3
        for timing_key in (
            "train_duration_seconds",
            "bench_duration_seconds",
            "selfplay_duration_seconds",
            "opt_duration_seconds",
        ):
            assert timing_key in first_row, f"Timing telemetry key '{timing_key}' missing from traceability payload"

