from agents.muzero.xai.decision_report import build_decision_report
from agents.muzero.xai.episode_narrative import build_episode_narrative
from agents.muzero.xai.search_tree_snapshot import build_search_snapshot


def test_decision_report_snapshot_deterministic():
    report = build_decision_report(
        step=3,
        actions=["move:u1:1,1", "capture:u2:vp0", "wait:u3"],
        probs=[0.6, 0.3, 0.1],
        priors=[0.5, 0.4, 0.1],
        values=[0.2, 0.9, -0.1],
        visits=[15, 8, 2],
        factor_contributions={"vp_pressure": 0.7, "enemy_threat": -0.4, "tempo": 0.2},
        entropy_threshold=1.2,
        margin_threshold=0.2,
        top_k=2,
    )
    expected = {
        "step": 3,
        "top_k": [
            {
                "action_id": "move:u1:1,1",
                "score": {
                    "policy_prob": 0.6,
                    "prior": 0.5,
                    "value": 0.2,
                    "visit_count": 15,
                },
            },
            {
                "action_id": "capture:u2:vp0",
                "score": {
                    "policy_prob": 0.3,
                    "prior": 0.4,
                    "value": 0.9,
                    "visit_count": 8,
                },
            },
        ],
        "margin": 0.3,
        "entropy": report["entropy"],
        "dominant_factors": [
            {"factor": "vp_pressure", "contribution": 0.7},
            {"factor": "enemy_threat", "contribution": -0.4},
            {"factor": "tempo", "contribution": 0.2},
        ],
        "instability": {
            "unstable": False,
            "reasons": {"high_entropy": False, "low_margin": False},
            "thresholds": {"entropy_threshold": 1.2, "margin_threshold": 0.2},
        },
    }
    # Entropy is deterministic float but asserted separately for tolerance.
    assert abs(report["entropy"] - 0.8979457248567797) < 1e-12
    expected["entropy"] = report["entropy"]
    assert report == expected
    assert "top_k" in report
    assert "margin" in report
    assert "dominant_factors" in report


def test_search_snapshot_snapshot_deterministic():
    snap = build_search_snapshot(
        actions=["move:u1:1,1", "capture:u2:vp0"],
        visits=[20, 10],
        probs=[0.7, 0.3],
        priors=[0.6, 0.4],
        values=[0.1, 0.8],
        max_nodes=2,
    )
    assert snap["root"]["expanded_children"] == 2
    assert snap["root"]["snapshot_children"] == 2
    assert snap["root"]["total_visits"] == 30
    assert len(snap["nodes"]) == 2
    assert snap["nodes"][0]["action_id"] == "move:u1:1,1"
    assert "visit_count" in snap["nodes"][0]["score"]
    assert "prior" in snap["nodes"][0]["score"]
    assert "value" in snap["nodes"][0]["score"]


def test_episode_narrative_snapshot_deterministic():
    decision_reports = [
        {
            "step": 0,
            "instability": {"unstable": False},
            "dominant_factors": [{"factor": "vp_pressure", "contribution": 0.5}],
        },
        {
            "step": 1,
            "instability": {"unstable": True},
            "dominant_factors": [
                {"factor": "enemy_threat", "contribution": -0.6},
                {"factor": "vp_pressure", "contribution": 0.3},
            ],
        },
    ]
    narrative = build_episode_narrative(
        rewards=[0.0, 1.0],
        actions=["move:u1:1,1", "capture:u2:vp0"],
        decision_reports=decision_reports,
        terminal_reason="natural_terminal",
    )
    assert "outcome" in narrative
    assert narrative["terminal_reason"] == "natural_terminal"
    assert narrative["unstable_decision_steps"] == [1]
    assert abs(narrative["unstable_decision_rate"] - 0.5) < 1e-12
    assert narrative["dominant_factors"][0]["factor"] == "vp_pressure"


def test_decision_report_with_heads_analysis_and_overrides():
    report = build_decision_report(
        step=5,
        actions=["fire:u1:enemy", "move:u1:cover", "wait:u1"],
        probs=[0.7, 0.2, 0.1],      # MCTS chosen action is fire
        priors=[0.2, 0.7, 0.1],     # Policy prior preferred move
        values=[0.85, 0.1, -0.2],
        visits=[25, 7, 3],
        rewards=[0.5, 0.0, 0.0],
        q_values=[0.82, 0.15, -0.1],
        u_values=[0.08, 0.12, 0.05],
        root_value=0.6,
        aux_outputs={
            "objective_logit": 1.5,
            "intent_logits": [0.1, 2.5, 0.2],
            "multi_vp_pred": [1.5, 3.2, 5.0],
            "consistency_drift": 0.04,
        },
    )

    assert "heads_analysis" in report
    heads = report["heads_analysis"]

    # 1. Policy head check
    policy_info = heads["policy_head"]
    assert policy_info["top_action_id"] == "move:u1:cover"
    assert policy_info["mcts_chosen_action_id"] == "fire:u1:enemy"
    assert policy_info["is_overridden_by_mcts"] is True
    assert policy_info["kl_divergence_mcts_prior"] > 0.0

    # 2. Value head check
    value_info = heads["value_head"]
    assert value_info["root_value"] == 0.6
    assert value_info["chosen_action_value"] == 0.85
    assert abs(value_info["value_spread"] - 1.05) < 1e-6

    # 3. Reward head check
    assert "reward_head" in heads
    reward_info = heads["reward_head"]
    assert reward_info["chosen_action_reward"] == 0.5
    assert reward_info["has_immediate_reward"] is True

    # 4. Aux heads check
    assert "auxiliary_heads" in heads
    aux = heads["auxiliary_heads"]
    assert "objective" in aux
    assert aux["objective"]["predicted_prob"] > 0.8
    assert aux["objective"]["predicted_conversion"] is True

    assert "intent" in aux
    assert aux["intent"]["predicted_intent_class"] == 1
    assert aux["intent"]["confidence"] > 0.7

    assert "multi_vp" in aux
    assert aux["multi_vp"]["min_distance"] == 1.5

    assert "consistency" in aux
    assert aux["consistency"]["is_stable"] is True

    # 5. Tactical insights check
    assert len(heads["tactical_insights"]) >= 2
    assert any("overrode" in s for s in heads["tactical_insights"])
    assert any("Objective Head predicts" in s for s in heads["tactical_insights"])

    # 6. Top-K custom metrics check
    top_action = report["top_k"][0]
    assert top_action["action_id"] == "fire:u1:enemy"
    assert top_action["score"]["reward"] == 0.5
    assert top_action["score"]["q_value"] == 0.82
    assert top_action["score"]["u_value"] == 0.08


def test_decision_report_with_tactical_heads():
    report = build_decision_report(
        step=8,
        actions=["flank:u2:left", "suppress:u1:target", "retreat:u3"],
        probs=[0.6, 0.3, 0.1],
        priors=[0.5, 0.3, 0.2],
        values=[0.6, 0.4, -0.3],
        visits=[18, 9, 3],
        aux_outputs={
            "threat_map_pred": [[0.8, 0.9], [0.1, 0.2]],
            "attrition_pred": [0.1, 0.9],
            "morale_pred": [-1.0, 0.5, 2.5, -0.5],
        },
    )

    assert "heads_analysis" in report
    heads = report["heads_analysis"]
    aux = heads["auxiliary_heads"]

    # Threat map assertions
    assert "threat_map" in aux
    threat = aux["threat_map"]
    assert threat["max_threat"] >= 0.8
    assert threat["high_threat_hex_count"] >= 2
    assert threat["threat_coverage_ratio"] == 0.5

    # Attrition assertions
    assert "attrition" in aux
    attr = aux["attrition"]
    assert attr["predicted_friendly_casualties"] == 0.1
    assert attr["predicted_enemy_casualties"] == 0.9
    assert attr["is_favorable_exchange"] is True
    assert attr["predicted_exchange_ratio"] > 1.0

    # Morale assertions
    assert "morale" in aux
    morale = aux["morale"]
    assert morale["predicted_morale_class"] == "SUPPRESSED"
    assert morale["suppression_risk_score"] > 0.5

    # Tactical insights check
    insights = heads["tactical_insights"]
    assert any("High battlefield threat detected" in s for s in insights)
    assert any("Favorable tactical exchange predicted" in s for s in insights)
    assert any("elevated morale/suppression risk" in s for s in insights)



