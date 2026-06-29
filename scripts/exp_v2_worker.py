from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import mlflow
import yaml


ALLOWED_APPLY_FILES = {
    "assault_sim/config/reward_config.json",
    "assault_sim/config/train_config.json",
}


@dataclass
class Paths:
    root: Path
    base: Path
    queue: Path
    archive_passed: Path
    archive_failed: Path
    runs: Path
    lock: Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_paths(root: Path) -> Paths:
    base = root / "experiments_v2"
    return Paths(
        root=root,
        base=base,
        queue=base / "queue",
        archive_passed=base / "archive" / "passed",
        archive_failed=base / "archive" / "failed",
        runs=base / "runs",
        lock=base / "worker.lock",
    )


def ensure_dirs(p: Paths) -> None:
    p.queue.mkdir(parents=True, exist_ok=True)
    p.archive_passed.mkdir(parents=True, exist_ok=True)
    p.archive_failed.mkdir(parents=True, exist_ok=True)
    p.runs.mkdir(parents=True, exist_ok=True)


def read_manifest(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def write_json(path: Path, obj: dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def run_command(command: str, cwd: Path, log_path: Path) -> int:
    with log_path.open("w", encoding="utf-8") as f:
        proc = subprocess.Popen(
            command,
            cwd=str(cwd),
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            f.write(line)
            f.flush()
            sys.stdout.write(line)
        return proc.wait()


def apply_change(root: Path, apply_cfg: dict[str, Any], backup_dir: Path) -> tuple[bool, str]:
    file_rel = str(apply_cfg.get("file", "")).replace("\\", "/").strip()
    key = str(apply_cfg.get("key", "")).strip()
    old_expected = apply_cfg.get("old")
    new_value = apply_cfg.get("new")
    if not file_rel or not key:
        return False, "missing apply.file/apply.key"
    if file_rel not in ALLOWED_APPLY_FILES:
        return False, f"unsupported apply.file: {file_rel}"
    target = (root / file_rel).resolve()
    if not target.exists():
        return False, f"missing target file: {file_rel}"
    data = json.loads(target.read_text(encoding="utf-8-sig"))
    if key not in data:
        return False, f"missing key in target: {key}"
    old_actual = data.get(key)
    if old_expected != old_actual:
        return False, f"old mismatch for {file_rel}:{key} expected={old_expected!r} actual={old_actual!r}"

    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"{target.name}.bak"
    shutil.copy2(target, backup_path)
    data[key] = new_value
    target.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return True, f"applied {file_rel}:{key} {old_actual!r}->{new_value!r}"


def restore_backup(root: Path, apply_cfg: dict[str, Any], backup_dir: Path) -> None:
    file_rel = str(apply_cfg.get("file", "")).replace("\\", "/").strip()
    target = root / file_rel
    backup_path = backup_dir / f"{target.name}.bak"
    if backup_path.exists():
        shutil.copy2(backup_path, target)


def process_manifest(paths: Paths, manifest_path: Path) -> None:
    manifest = read_manifest(manifest_path)
    exp_id = str(manifest.get("id", "")).strip() or manifest_path.stem
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = paths.runs / f"{exp_id}_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)

    running_manifest = run_dir / "manifest.yaml"
    shutil.copy2(manifest_path, running_manifest)

    result: dict[str, Any] = {
        "id": exp_id,
        "status": "running",
        "manifest_source": str(manifest_path),
        "run_dir": str(run_dir),
        "started_at_utc": utc_now(),
        "finished_at_utc": None,
        "apply_ok": False,
        "train_exit_code": None,
        "gate_exit_code": None,
    }
    write_json(run_dir / "result.json", result)

    tracking_uri = f"file:{(paths.base / 'mlruns').resolve()}"
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment("assault_experiments_v2")

    apply_cfg = manifest.get("apply", {}) or {}
    backup_dir = run_dir / "backup"

    with mlflow.start_run(run_name=exp_id):
        mlflow.log_param("experiment_id", exp_id)
        mlflow.log_param("surface", str(manifest.get("surface", "")))
        mlflow.log_param("manifest", manifest_path.name)

        ok, apply_msg = apply_change(paths.root, apply_cfg, backup_dir)
        mlflow.log_param("apply_message", apply_msg)
        if not ok:
            result["status"] = "apply_failed"
            result["finished_at_utc"] = utc_now()
            write_json(run_dir / "result.json", result)
            shutil.move(str(manifest_path), str(paths.archive_failed / manifest_path.name))
            return

        result["apply_ok"] = True
        write_json(run_dir / "result.json", result)

        train_cmd = str((manifest.get("run", {}) or {}).get("train_command", "")).strip()
        gate_cmd = str((manifest.get("run", {}) or {}).get("gate_command", "")).strip()
        if not train_cmd or not gate_cmd:
            restore_backup(paths.root, apply_cfg, backup_dir)
            result["status"] = "invalid_manifest"
            result["finished_at_utc"] = utc_now()
            write_json(run_dir / "result.json", result)
            shutil.move(str(manifest_path), str(paths.archive_failed / manifest_path.name))
            return

        train_exit = run_command(train_cmd, paths.root, run_dir / "train.log")
        result["train_exit_code"] = train_exit
        mlflow.log_metric("train_exit_code", train_exit)
        write_json(run_dir / "result.json", result)
        if train_exit != 0:
            restore_backup(paths.root, apply_cfg, backup_dir)
            result["status"] = "train_failed"
            result["finished_at_utc"] = utc_now()
            write_json(run_dir / "result.json", result)
            shutil.move(str(manifest_path), str(paths.archive_failed / manifest_path.name))
            return

        gate_exit = run_command(gate_cmd, paths.root, run_dir / "gate.log")
        result["gate_exit_code"] = gate_exit
        mlflow.log_metric("gate_exit_code", gate_exit)
        write_json(run_dir / "result.json", result)
        if gate_exit != 0:
            restore_backup(paths.root, apply_cfg, backup_dir)
            result["status"] = "gate_failed"
            result["finished_at_utc"] = utc_now()
            write_json(run_dir / "result.json", result)
            shutil.move(str(manifest_path), str(paths.archive_failed / manifest_path.name))
            return

        result["status"] = "success"
        result["finished_at_utc"] = utc_now()
        write_json(run_dir / "result.json", result)
        shutil.move(str(manifest_path), str(paths.archive_passed / manifest_path.name))


def pending_manifests(queue_dir: Path) -> list[Path]:
    return sorted(queue_dir.glob("*.yaml"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Experiments V2 queue worker")
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument("--poll-seconds", type=int, default=10)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    paths = build_paths(root)
    ensure_dirs(paths)

    if paths.lock.exists():
        print(f"Worker already running (lock file exists): {paths.lock}")
        return 2
    paths.lock.write_text(json.dumps({"pid": os.getpid(), "started_at_utc": utc_now()}, indent=2), encoding="utf-8")

    try:
        while True:
            manifests = pending_manifests(paths.queue)
            print(f"[worker] pending={len(manifests)}")
            if manifests:
                process_manifest(paths, manifests[0])
            if args.once:
                break
            time.sleep(max(1, args.poll_seconds))
    finally:
        if paths.lock.exists():
            paths.lock.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

