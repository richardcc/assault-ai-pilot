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
            '"config_preflight_warnings":["custom.preflight.warning"]}}'
        ),
        encoding="utf-8",
    )
    (run_dir / "xai" / "bench_eval_20260703_000001.json").write_text(
        (
            '{"scenario_id":"s1","phase_2_9_promotion_gate":{"status":"PASS"},'
            '"results":['
            '{"matchup_profile":"muzero_selfplay","policy_by_side":{},'
            '"eval_decision_summary":{"decision_ownership_by_side":{"IT":{"rows":2},"US":{"rows":3}}}},'
            '{"matchup_profile":"random_selfplay","policy_by_side":{"it":"random","us":"random"},'
            '"eval_decision_summary":{"decision_ownership_by_side":{"IT":{"rows":1},"US":{"rows":1}}}},'
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
    assert len(eval_results) == 2
    assert eval_results[0]["controller_by_side"] == {"IT": "Unknown", "US": "Unknown"}
    assert eval_results[0]["controller_unknown_label_count"] == 2
    assert eval_results[1]["policy_by_side"] == {"IT": "mcts", "US": "random"}
    assert eval_results[1]["controller_by_side"] == {"IT": "MuZero", "US": "Random"}
    assert model["eval_history"][0]["controller_unknown_label_rows"] == 1
    obj_cfg = model["train_history"][0]["objective_reward_config"]
    assert obj_cfg["objective_signal"]["opportunity_near_vp_max_dist"] == 2.0
    assert obj_cfg["objective_head"]["progress_positive_threshold"] == 0.0
    assert obj_cfg["objective_reporting"]["conversion_window_steps_after_progress"] == 2
    assert obj_cfg["reward_shaping"]["capture_bonus"] == 0.55
    assert obj_cfg["preflight_warnings"] == ["custom.preflight.warning"]


def test_reporting_catalog_can_opt_in_random_selfplay(tmp_path: Path) -> None:
    repo = tmp_path
    run_dir = repo / "runs" / "muzero_abcd1234"
    (run_dir / "checkpoints").mkdir(parents=True, exist_ok=True)
    (run_dir / "metrics").mkdir(parents=True, exist_ok=True)
    (run_dir / "xai").mkdir(parents=True, exist_ok=True)
    (run_dir / "checkpoints" / "iter_1.pt").write_text("x", encoding="utf-8")
    (run_dir / "run_manifest.json").write_text('{"scenario_id":"s1","config":{"iterations":2}}', encoding="utf-8")
    (run_dir / "xai" / "bench_eval_20260703_000001.json").write_text(
        (
            '{"scenario_id":"s1","results":['
            '{"matchup_profile":"muzero_selfplay","policy_by_side":{"it":"mcts","us":"mcts"}},'
            '{"matchup_profile":"random_selfplay","policy_by_side":{"it":"random","us":"random"}}'
            ']}'
        ),
        encoding="utf-8",
    )

    payload = build_reporting_catalog(repo_root=repo, include_random_selfplay=True)
    muzero_engine = next(e for e in payload["engines"] if e["engine"] == "muzero")
    model = muzero_engine["models"][0]
    profiles = [str(r.get("matchup_profile", "")) for r in model["eval_history"][0]["results"]]
    assert profiles == ["muzero_selfplay", "random_selfplay"]


def test_reporting_catalog_preserves_eval_decision_steps_top_rows(tmp_path: Path) -> None:
    repo = tmp_path
    run_dir = repo / "runs" / "efficientzero_v2_abcd1234"
    (run_dir / "checkpoints").mkdir(parents=True, exist_ok=True)
    (run_dir / "metrics").mkdir(parents=True, exist_ok=True)
    (run_dir / "xai").mkdir(parents=True, exist_ok=True)
    (run_dir / "checkpoints" / "iter_1.pt").write_text("x", encoding="utf-8")
    (run_dir / "run_manifest.json").write_text('{"scenario_id":"s1","config":{"iterations":2}}', encoding="utf-8")
    (run_dir / "xai" / "bench_eval_20260703_000001.json").write_text(
        (
            '{"scenario_id":"s1","results":['
            '{"agent_name":"efficientzero_v2_stub","matchup_profile":"muzero_selfplay",'
            '"eval_decision_steps_top":[{"step":0,"unit_side":"IT","action_id":"MOVE:IT_1:1:1","mcts_action_candidates":[{"selected_action":true,"decision_components":{"vp_horizon_component":0.5}}]}]}'
            ']}'
        ),
        encoding="utf-8",
    )

    payload = build_reporting_catalog(repo_root=repo, runs_roots_rel=("runs",))
    ez_engine = next(e for e in payload["engines"] if e["engine"] == "efficientzero_v2")
    model = ez_engine["models"][0]
    result_row = model["eval_history"][0]["results"][0]
    steps_top = list(result_row.get("eval_decision_steps_top", []) or [])
    assert len(steps_top) == 1
    candidate = (steps_top[0].get("mcts_action_candidates") or [])[0]
    assert candidate["decision_components"]["vp_horizon_component"] == 0.5


def test_reporting_catalog_preserves_unit_prefilter_fields_in_eval_decision_steps_top(tmp_path: Path) -> None:
    repo = tmp_path
    run_dir = repo / "runs" / "efficientzero_v2_abcd1234"
    (run_dir / "checkpoints").mkdir(parents=True, exist_ok=True)
    (run_dir / "metrics").mkdir(parents=True, exist_ok=True)
    (run_dir / "xai").mkdir(parents=True, exist_ok=True)
    (run_dir / "checkpoints" / "iter_1.pt").write_text("x", encoding="utf-8")
    (run_dir / "run_manifest.json").write_text('{"scenario_id":"s1","config":{"iterations":2}}', encoding="utf-8")
    (run_dir / "xai" / "bench_eval_20260703_000001.json").write_text(
        (
            '{"scenario_id":"s1","results":['
            '{"agent_name":"efficientzero_v2_stub","matchup_profile":"muzero_selfplay",'
            '"eval_decision_steps_top":[{"step":0,'
            '"unit_prefilter_enabled":true,'
            '"unit_prefilter_selected_unit_id":"US_3",'
            '"unit_prefilter_constrained_count":2,'
            '"unit_prefilter_global_count":7}]}'
            ']}'
        ),
        encoding="utf-8",
    )

    payload = build_reporting_catalog(repo_root=repo, runs_roots_rel=("runs",))
    ez_engine = next(e for e in payload["engines"] if e["engine"] == "efficientzero_v2")
    model = ez_engine["models"][0]
    result_row = model["eval_history"][0]["results"][0]
    steps_top = list(result_row.get("eval_decision_steps_top", []) or [])
    assert len(steps_top) == 1
    top = dict(steps_top[0] or {})
    assert top["unit_prefilter_enabled"] is True
    assert top["unit_prefilter_selected_unit_id"] == "US_3"
    assert top["unit_prefilter_constrained_count"] == 2
    assert top["unit_prefilter_global_count"] == 7


def test_reporting_catalog_groups_curriculum_retrains_under_lineage_model(tmp_path: Path) -> None:
    repo = tmp_path
    run1 = repo / "runs_curriculum" / "efficientzero_v2_root1111"
    run2 = repo / "runs_curriculum" / "efficientzero_v2_child2222"
    (run1 / "checkpoints").mkdir(parents=True, exist_ok=True)
    (run1 / "metrics").mkdir(parents=True, exist_ok=True)
    (run1 / "xai").mkdir(parents=True, exist_ok=True)
    (run2 / "checkpoints").mkdir(parents=True, exist_ok=True)
    (run2 / "metrics").mkdir(parents=True, exist_ok=True)
    (run2 / "xai").mkdir(parents=True, exist_ok=True)
    (run1 / "checkpoints" / "final.pt").write_text("x", encoding="utf-8")
    (run2 / "checkpoints" / "final.pt").write_text("y", encoding="utf-8")

    (run1 / "run_manifest.json").write_text(
        '{"scenario_id":"s1","config":{"iterations":2,"matchup_modes":["self_vs_self"]}}',
        encoding="utf-8",
    )
    (run2 / "run_manifest.json").write_text(
        (
            '{"scenario_id":"s1","config":{"iterations":2,'
            '"matchup_modes":["self_vs_self","self_vs_random"],'
            '"resume_checkpoint":"'
            + str((run1 / "checkpoints" / "final.pt").as_posix())
            + '"}}'
        ),
        encoding="utf-8",
    )

    payload = build_reporting_catalog(repo_root=repo, runs_roots_rel=("runs_curriculum",))
    ez_engine = next(e for e in payload["engines"] if e["engine"] == "efficientzero_v2")
    assert len(ez_engine["models"]) == 1
    model = ez_engine["models"][0]
    assert model["lineage_root_run_id"] == "efficientzero_v2_root1111"
    run_ids = [str(r.get("run_id", "")) for r in model["train_history"]]
    assert set(run_ids) == {"efficientzero_v2_root1111", "efficientzero_v2_child2222"}
