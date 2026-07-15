import json
from pathlib import Path

from agents.muzero.xai.timeline_exporter import export_muzero_episode_timeline


def test_timeline_export_keeps_intent_and_objective_fields(tmp_path: Path):
    run_id = "muzero_test_intent"
    run_dir = tmp_path / "runs" / run_id
    events_dir = run_dir / "events"
    events_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "run_manifest.json").write_text(
        json.dumps({"scenario_id": "battaglia_cittadina_2_1", "seed": 123}),
        encoding="utf-8",
    )

    payload = {
        "type": "TransitionEvent",
        "payload": {
            "iteration": 0,
            "episode": 0,
            "step": 0,
            "game_turn": 1,
            "to_play": "IT",
            "action_id": "MOVE:IT_1:3:4",
            "action_kind": "MOVE",
            "unit_id": "IT_1",
            "unit_side": "IT",
            "unit_label": "IT_RIFLES_43",
            "reward_target": 0.25,
            "done": False,
            "transition_info": {
                "plan_intent": "CAPTURE",
                "plan_focus_vp_id": "VP_2",
                "plan_team_focus_vp_id": "VP_2",
                "intent_alignment_stub": 1.0,
                "legal_capture_options": 3,
                "legal_action_count": 7,
                "legal_action_types": ["MOVE", "FIRE"],
                "policy_top_action": "MOVE:IT_1:3:4",
                "mcts_chosen_action": "MOVE:IT_1:3:4",
                "policy_overridden_by_mcts": 0,
                "mcts_action_candidates": [
                    {
                        "action_id": "MOVE:IT_1:3:4",
                        "policy_prior": 0.52,
                        "q_estimate": 0.31,
                        "reward_estimate": 0.12,
                        "exploration_bonus_u": 0.08,
                        "final_score": 0.39,
                        "vp_progress_delta": 1.0,
                    }
                ],
                "why_action_vs_vp": {
                    "top_k": 5,
                    "chosen_action_id": "MOVE:IT_1:3:4",
                    "vp_best_action_id": "MOVE:IT_1:3:4",
                    "delta_score": 0.0,
                    "score_components_priority": ["Q", "U"],
                    "explanation": "selected action is also best toward VP",
                    "candidate_actions": [
                        {
                            "action_id": "MOVE:IT_1:3:4",
                            "policy_prior": 0.52,
                            "q_estimate": 0.31,
                            "reward_estimate": 0.12,
                            "exploration_bonus_u": 0.08,
                            "final_score": 0.39,
                            "vp_progress_delta": 1.0,
                        }
                    ],
                },
                "why_action_vs_vp_text": "selected action is also best toward VP",
                "objective_had_opportunity": 1,
                "objective_distance_before": 2.0,
                "objective_distance_after": 1.0,
                "objective_min_dist_before": 2.0,
                "objective_min_dist_after": 1.0,
                "objective_progress_delta": 1.0,
                "objective_converted": 0,
                "objective_best_vp_id": "VP_2",
                "vp_distance_vector": {"VP_2": 2.0, "VP_4": 3.0},
                "vp_distance_vector_size": 2,
                "objective_signal_definition_version": "vp_objective_v2",
            },
            "chosen_action_prob": 0.71,
            "mcts_entropy": 0.45,
            "mcts_margin": 0.25,
            "mcts_total_visits": 32,
            "mcts_active_actions": 6,
            "predicted_value_root": 0.34,
            "dynamics_pred_reward": 0.12,
            "dynamics_next_latent_l2": 2.8,
            "dynamics_delta_l2": 0.7,
            "policy_top_actions": ["MOVE:IT_1:3:4", "WAIT:IT_1"],
            "policy_top_probs": [0.71, 0.19],
            "latent_top_indices": [3, 11],
            "latent_top_values": [1.3, 1.1],
            "latent_l2_norm": 5.4,
            "runtime_events": [],
            "units_snapshot": [],
        },
    }
    (events_dir / "train_events.jsonl").write_text(
        json.dumps(payload) + "\n",
        encoding="utf-8",
    )

    out = export_muzero_episode_timeline(
        repo_root=tmp_path,
        run_id=run_id,
        iteration=0,
        episode=0,
    )

    row = out["transitions"][0]
    assert row["plan_intent"] == "CAPTURE"
    assert row["plan_focus_vp_id"] == "VP_2"
    assert row["plan_team_focus_vp_id"] == "VP_2"
    assert row["intent_alignment_stub"] == 1.0
    assert row["legal_capture_options"] == 3
    assert row["legal_action_count"] == 7
    assert row["legal_action_types"] == ["MOVE", "FIRE"]
    assert row["policy_top_action"] == "MOVE:IT_1:3:4"
    assert row["mcts_chosen_action"] == "MOVE:IT_1:3:4"
    assert row["policy_overridden_by_mcts"] == 0
    assert row["mcts_action_candidates"][0]["action_id"] == "MOVE:IT_1:3:4"
    assert row["why_action_vs_vp"]["chosen_action_id"] == "MOVE:IT_1:3:4"
    assert row["why_action_vs_vp_text"] == "selected action is also best toward VP"
    assert row["objective_had_opportunity"] == 1
    assert row["objective_distance_before"] == 2.0
    assert row["objective_distance_after"] == 1.0
    assert row["objective_min_dist_before"] == 2.0
    assert row["objective_min_dist_after"] == 1.0
    assert row["objective_progress_delta"] == 1.0
    assert row["objective_converted"] == 0
    assert row["objective_best_vp_id"] == "VP_2"
    assert row["vp_distance_vector"] == {"VP_2": 2.0, "VP_4": 3.0}
    assert row["vp_distance_vector_size"] == 2
    assert row["objective_signal_definition_version"] == "vp_objective_v2"
    assert row["chosen_action_prob"] == 0.71
    assert row["mcts_entropy"] == 0.45
    assert row["mcts_margin"] == 0.25
    assert row["mcts_total_visits"] == 32
    assert row["mcts_active_actions"] == 6
    assert row["predicted_value_root"] == 0.34
    assert row["dynamics_pred_reward"] == 0.12
    assert row["dynamics_next_latent_l2"] == 2.8
    assert row["dynamics_delta_l2"] == 0.7
    assert row["policy_top_actions"] == ["MOVE:IT_1:3:4", "WAIT:IT_1"]
    assert row["policy_top_probs"] == [0.71, 0.19]
    assert row["latent_top_indices"] == [3, 11]
    assert row["latent_top_values"] == [1.3, 1.1]
    assert row["latent_l2_norm"] == 5.4


def test_timeline_export_decision_fields_are_backward_compatible(tmp_path: Path):
    run_id = "muzero_test_intent_backcompat"
    run_dir = tmp_path / "runs" / run_id
    events_dir = run_dir / "events"
    events_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_manifest.json").write_text(
        json.dumps({"scenario_id": "battaglia_cittadina_2_1", "seed": 123}),
        encoding="utf-8",
    )
    payload = {
        "type": "TransitionEvent",
        "payload": {
            "iteration": 0,
            "episode": 0,
            "step": 0,
            "to_play": "IT",
            "action_id": "WAIT:IT_1",
            "transition_info": {},
        },
    }
    (events_dir / "train_events.jsonl").write_text(json.dumps(payload) + "\n", encoding="utf-8")
    out = export_muzero_episode_timeline(repo_root=tmp_path, run_id=run_id, iteration=0, episode=0)
    row = out["transitions"][0]
    assert row["legal_action_count"] is None
    assert row["legal_action_types"] == []
    assert row["policy_top_action"] == ""
    assert row["mcts_chosen_action"] == "WAIT:IT_1"
    assert row["policy_overridden_by_mcts"] is None
    assert row["mcts_action_candidates"] == []
    assert row["why_action_vs_vp"] == {}
    assert row["why_action_vs_vp_text"] == ""
    assert row["objective_min_dist_before"] == -1.0
    assert row["objective_min_dist_after"] == -1.0
    assert row["objective_best_vp_id"] == ""
    assert row["vp_distance_vector"] == {}
    assert row["vp_distance_vector_size"] == 0
