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
