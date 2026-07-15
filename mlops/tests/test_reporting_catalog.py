from pathlib import Path

from mlops.reporting.build_catalog import build_reporting_catalog


def test_reporting_catalog_groups_train_and_eval(tmp_path: Path) -> None:
    repo = tmp_path
    run_dir = repo / "runs" / "muzero_abcd1234"
    (run_dir / "checkpoints").mkdir(parents=True, exist_ok=True)
    (run_dir / "metrics").mkdir(parents=True, exist_ok=True)
    (run_dir / "xai").mkdir(parents=True, exist_ok=True)
    (run_dir / "checkpoints" / "iter_1.pt").write_text("x", encoding="utf-8")
    (run_dir / "run_manifest.json").write_text(
        (
            '{"scenario_id":"s1","config":{"iterations":2,"resume_checkpoint":"",'
            '"objective_signal":{"opportunity_near_vp_max_dist":2.0},'
            '"objective_head":{"progress_positive_threshold":0.0},'
            '"objective_reporting":{"conversion_window_steps_after_progress":2},'
            '"selfplay":{"reward_shaping":{"capture_bonus":0.55}},'
            '"config_preflight_warnings":["missing.selfplay.reward_shaping"]}}'
        ),
        encoding="utf-8",
    )
    (run_dir / "xai" / "bench_eval_20260703_000001.json").write_text(
        (
            '{"scenario_id":"s1","phase_2_9_promotion_gate":{"status":"PASS"},'
            '"results":['
            '{"matchup_profile":"muzero_selfplay","policy_by_side":{},'
            '"eval_decision_summary":{"decision_ownership_by_side":{"IT":{"rows":2},"US":{"rows":3}}}},'
            '{"matchup_profile":"muzero_vs_random_side_a","policy_by_side":{"it":"mcts","us":"random"},'
            '"eval_decision_summary":{"decision_ownership_by_side":{"IT":{"rows":1},"US":{"rows":1}}}}'
            ']}'
        ),
        encoding="utf-8",
    )
    mlrun = repo / "mlruns" / "0" / "run_a"
    (mlrun / "params").mkdir(parents=True, exist_ok=True)
    (mlrun / "tags").mkdir(parents=True, exist_ok=True)
    (mlrun / "params" / "run_id").write_text("muzero_abcd1234", encoding="utf-8")
    (mlrun / "tags" / "mlflow.source.git.commit").write_text("deadbeef", encoding="utf-8")

    payload = build_reporting_catalog(repo_root=repo)
    assert payload["engines"][0]["engine"] == "efficientzero_v2"
    muzero_engine = next(e for e in payload["engines"] if e["engine"] == "muzero")
    assert len(muzero_engine["models"]) == 1
    model = muzero_engine["models"][0]
    assert len(model["train_history"]) == 1
    assert len(model["eval_history"]) == 1
    assert model["train_history"][0]["git_commit"] == "deadbeef"
    eval_results = model["eval_history"][0]["results"]
    assert eval_results[0]["controller_by_side"] == {"IT": "Legacy/Unlabeled", "US": "Legacy/Unlabeled"}
    assert eval_results[0]["controller_legacy_unlabeled_count"] == 2
    assert eval_results[1]["policy_by_side"] == {"IT": "mcts", "US": "random"}
    assert eval_results[1]["controller_by_side"] == {"IT": "MuZero", "US": "Random"}
    assert model["eval_history"][0]["controller_legacy_unlabeled_rows"] == 1
    obj_cfg = model["train_history"][0]["objective_reward_config"]
    assert obj_cfg["objective_signal"]["opportunity_near_vp_max_dist"] == 2.0
    assert obj_cfg["objective_head"]["progress_positive_threshold"] == 0.0
    assert obj_cfg["objective_reporting"]["conversion_window_steps_after_progress"] == 2
    assert obj_cfg["reward_shaping"]["capture_bonus"] == 0.55
    assert obj_cfg["preflight_warnings"] == ["missing.selfplay.reward_shaping"]
