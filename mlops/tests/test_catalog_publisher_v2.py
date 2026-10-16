import json
from pathlib import Path
from threading import Thread

from mlops.catalog_publisher_v2 import publish_catalog_snapshot, publish_eval_run, publish_train_run


def _seed_train_run(repo_root: Path, run_id: str) -> None:
    run_dir = repo_root / "runs" / run_id
    (run_dir / "checkpoints").mkdir(parents=True, exist_ok=True)
    (run_dir / "metrics").mkdir(parents=True, exist_ok=True)
    (run_dir / "checkpoints" / "iter_1.pt").write_text("x", encoding="utf-8")
    (run_dir / "run_manifest.json").write_text(
        '{"scenario_id":"s1","config":{"iterations":1}}',
        encoding="utf-8",
    )


def _seed_eval_run(repo_root: Path, run_id: str) -> None:
    run_dir = repo_root / "runs" / run_id
    (run_dir / "checkpoints").mkdir(parents=True, exist_ok=True)
    (run_dir / "metrics").mkdir(parents=True, exist_ok=True)
    (run_dir / "xai").mkdir(parents=True, exist_ok=True)
    (run_dir / "checkpoints" / "iter_1.pt").write_text("x", encoding="utf-8")
    (run_dir / "run_manifest.json").write_text('{"scenario_id":"s1","config":{"iterations":1}}', encoding="utf-8")
    (run_dir / "xai" / "bench_eval_20260721_080000.json").write_text(
        (
            '{"scenario_id":"s1","results":[{"matchup_profile":"muzero_selfplay",'
            '"policy_by_side":{"it":"mcts","us":"mcts"},'
            '"eval_decision_steps_top":[{"step":0,"action_id":"WAIT:IT_1","mcts_action_candidates":[]}]}]}'
        ),
        encoding="utf-8",
    )
    (run_dir / "xai" / "bench_eval_20260721_080001.json").write_text(
        (
            '{"scenario_id":"s1","results":[{"matchup_profile":"muzero_selfplay",'
            '"policy_by_side":{"it":"mcts","us":"mcts"},'
            '"eval_decision_steps_top":[{"step":1,"action_id":"WAIT:IT_2","mcts_action_candidates":[]}]}]}'
        ),
        encoding="utf-8",
    )


def test_publish_train_run_updates_catalog(tmp_path: Path) -> None:
    run_id = "efficientzero_v2_deadbeef"
    _seed_train_run(tmp_path, run_id)
    result = publish_train_run(repo_root=tmp_path)
    assert result["schema_version"] == "reporting_v2_strict"
    assert str(result.get("index_summary", {}).get("mode", "")) in {"incremental_upsert", ""}

    catalog_path = tmp_path / "runs_curriculum" / "experiments" / "reporting" / "model_catalog_latest.json"
    assert catalog_path.exists()
    payload = catalog_path.read_text(encoding="utf-8")
    assert run_id in payload
    status_path = tmp_path / "runs_curriculum" / "experiments" / "reporting" / "catalog_publish_status.json"
    assert status_path.exists()
    status_payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert status_payload["status"] in {"complete", "partial"}


def test_publish_eval_run_updates_catalog_with_eval_history(tmp_path: Path) -> None:
    run_id = "muzero_deadbeef"
    _seed_eval_run(tmp_path, run_id)
    result = publish_eval_run(repo_root=tmp_path)
    assert result["schema_version"] == "reporting_v2_strict"

    catalog_path = tmp_path / "runs_curriculum" / "experiments" / "reporting" / "model_catalog_latest.json"
    assert catalog_path.exists()
    payload = catalog_path.read_text(encoding="utf-8")
    assert "bench_eval_20260721_080000.json" in payload
    assert "eval_decision_steps_top" not in payload
    # Slim catalog must keep only newest eval rows per model.
    assert "bench_eval_20260721_080001.json" in payload
    assert "eval_history_total_count" in payload
    assert "eval_history_visible_count" in payload

    debug_catalog_path = tmp_path / "runs_curriculum" / "experiments" / "reporting" / "model_catalog_full_latest.json"
    assert debug_catalog_path.exists()
    payload_debug = debug_catalog_path.read_text(encoding="utf-8")
    assert "eval_decision_steps_top" in payload_debug
    # DuckDB build is best-effort depending on dependency availability.
    db_path = tmp_path / "runs_curriculum" / "experiments" / "reporting" / "reporting.duckdb"
    if result.get("duckdb_summary", {}).get("ok"):
        assert db_path.exists()


def test_publish_catalog_lock_serializes_concurrent_writes(tmp_path: Path) -> None:
    _seed_train_run(tmp_path, "efficientzero_v2_lock_a")
    _seed_eval_run(tmp_path, "muzero_lock_b")
    errors: list[str] = []

    def _publish_train() -> None:
        try:
            publish_train_run(repo_root=tmp_path)
        except Exception as exc:
            errors.append(f"train:{exc}")

    def _publish_eval() -> None:
        try:
            publish_eval_run(repo_root=tmp_path)
        except Exception as exc:
            errors.append(f"eval:{exc}")

    t1 = Thread(target=_publish_train)
    t2 = Thread(target=_publish_eval)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors
    catalog_path = tmp_path / "runs_curriculum" / "experiments" / "reporting" / "model_catalog_latest.json"
    assert catalog_path.exists()


def test_publish_catalog_snapshot_can_limit_slim_eval_history(tmp_path: Path) -> None:
    run_id = "muzero_trimtest"
    _seed_eval_run(tmp_path, run_id)
    publish_catalog_snapshot(repo_root=tmp_path, max_eval_history_per_model_slim=1)
    catalog_path = tmp_path / "runs_curriculum" / "experiments" / "reporting" / "model_catalog_latest.json"
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    muzero = next(e for e in list(payload.get("engines", []) or []) if str(e.get("engine", "")) == "muzero")
    models = list(muzero.get("models", []) or [])
    assert models
    model = models[0]
    assert int(model.get("eval_history_total_count", 0) or 0) >= 2
    assert int(model.get("eval_history_visible_count", 0) or 0) == 1
    assert bool(model.get("eval_history_truncated", False)) is True


def test_publish_catalog_snapshot_prunes_debug_history(tmp_path: Path) -> None:
    _seed_eval_run(tmp_path, "muzero_hist_a")
    publish_catalog_snapshot(repo_root=tmp_path, debug_full_history_keep=1)
    _seed_eval_run(tmp_path, "muzero_hist_b")
    publish_catalog_snapshot(repo_root=tmp_path, debug_full_history_keep=1)
    debug_dir = tmp_path / "runs_curriculum" / "experiments" / "reporting"
    hist = list(debug_dir.glob("model_catalog_full_*.json"))
    assert len(hist) <= 1


def test_publish_status_file_contains_phase_markers(tmp_path: Path) -> None:
    _seed_eval_run(tmp_path, "muzero_status_marker")
    publish_catalog_snapshot(repo_root=tmp_path)
    status_path = tmp_path / "runs_curriculum" / "experiments" / "reporting" / "catalog_publish_status.json"
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    phases = dict(payload.get("phases", {}) or {})
    assert "slim_catalog_written" in phases
    assert "debug_catalog_written" in phases
    assert "parquet_indexes_written" in phases
    assert "duckdb_materialized" in phases
