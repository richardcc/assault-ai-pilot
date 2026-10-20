from __future__ import annotations

import logging
import os
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path

from assault_bench.transform_ops import to_dict_rows

def _is_mlflow_online() -> bool:
    uri = str(os.environ.get("MLFLOW_TRACKING_URI", "")).strip()
    if not uri or not (uri.startswith("http://") or uri.startswith("https://")):
        return True
    import socket
    from urllib.parse import urlparse
    parsed = urlparse(uri)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=0.25):
            return True
    except Exception:
        return False


def start_mlflow_run(experiment_name: str, run_name: str):
    disable_mlflow = str(os.environ.get("ASSAULT_BENCH_DISABLE_MLFLOW", "")).strip().lower()
    if disable_mlflow in {"1", "true", "yes", "on"} or not _is_mlflow_online():
        return None, nullcontext()
    try:
        import mlflow  # type: ignore
    except Exception:
        return None, nullcontext()
    try:
        logging.getLogger("mlflow").setLevel(logging.WARNING)
        logging.getLogger("mlflow.tracking").setLevel(logging.WARNING)
        mlflow.set_experiment(str(experiment_name))
        ctx = mlflow.start_run(run_name=str(run_name) if str(run_name).strip() else None)
        return mlflow, ctx
    except Exception as exc:
        print(f"[Bench][WARN] MLflow disabled for this benchmark: {exc}", flush=True)
        return None, nullcontext()


def mlflow_log_metrics(mlflow_mod, metrics: dict) -> None:
    if mlflow_mod is None:
        return
    for k, v in (metrics or {}).items():
        if isinstance(v, (int, float)):
            try:
                mlflow_mod.log_metric(str(k), float(v))
            except Exception:
                continue


def persist_bench_artifacts(
    *,
    run_id: str,
    scenario_id: str,
    run_root: Path,
    payload: dict,
    results: list,
    bench_replay_episodes: list,
    json_dumps_fn,
    persist_replay_episode_files: bool = True,
) -> None:
    if not str(run_id or "").strip():
        return
    bench_stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    run_xai_dir = run_root / str(run_id) / "xai"
    run_xai_dir.mkdir(parents=True, exist_ok=True)
    replay_eps_dir = run_xai_dir / "bench_replay_episodes"
    replay_eps_dir.mkdir(parents=True, exist_ok=True)
    episodes_meta: list[dict[str, object]] = []
    for idx, ep_row in enumerate(to_dict_rows(bench_replay_episodes)):
        episode_index = int(ep_row.get("episode_index", idx) or idx)
        seed = int(ep_row.get("seed", 0) or 0)
        agent_name = str(ep_row.get("agent_name", "") or "")
        transitions = list(ep_row.get("transitions", []) or [])
        episode_file = f"episode_{episode_index:04d}.json"
        episode_rel_path = f"bench_replay_episodes/{episode_file}"
        ep_scenario_id = str(ep_row.get("scenario_id", scenario_id))
        if bool(persist_replay_episode_files):
            episode_payload = {
                "schema_version": "bench_replay_episode_v2",
                "run_id": str(run_id),
                "scenario_id": ep_scenario_id,
                "bench_id": str(bench_stamp),
                "episode_index": int(episode_index),
                "seed": int(seed),
                "agent_name": str(agent_name),
                "transitions": transitions,
            }
            (replay_eps_dir / episode_file).write_text(
                json_dumps_fn(episode_payload, indent=2),
                encoding="utf-8",
            )
        episodes_meta.append(
            {
                "episode_index": int(episode_index),
                "seed": int(seed),
                "agent_name": str(agent_name),
                "scenario_id": ep_scenario_id,
                "transitions": int(len(transitions)),
                "episode_path": (str(episode_rel_path) if bool(persist_replay_episode_files) else ""),
            }
        )
    bench_replay_index_payload = {
        "schema_version": "bench_replay_index_v2",
        "run_id": str(run_id),
        "scenario_id": str(scenario_id),
        "bench_id": str(bench_stamp),
        "episodes_meta": episodes_meta,
    }
    bench_replay_index_out = run_xai_dir / "bench_replay_index_latest.json"
    bench_replay_index_out.write_text(
        json_dumps_fn(bench_replay_index_payload, indent=2),
        encoding="utf-8",
    )
    bench_replay_index_hist = run_xai_dir / f"bench_replay_index_{bench_stamp}.json"
    bench_replay_index_hist.write_text(
        json_dumps_fn(bench_replay_index_payload, indent=2),
        encoding="utf-8",
    )
    bench_eval_hist = run_xai_dir / f"bench_eval_{bench_stamp}.json"
    bench_eval_hist.write_text(
        json_dumps_fn(dict(payload or {}), indent=2),
        encoding="utf-8",
    )
    try:
        from mlops.storage_v2 import write_eval_bundle_v2

        selected_row = next(
            (
                r
                for r in list(results or [])
                if str(r.agent_name or "").strip().lower()
                in {"ezv2_stub", "efficientzero_v2_stub", "muzero_stub"}
            ),
            results[0] if results else None,
        )
        if selected_row is not None:
            model_id = str(run_id)
            eval_id = f"{run_id}__{bench_stamp}"
            full_step_rows = []
            if bench_replay_episodes:
                first_ep = to_dict_rows(bench_replay_episodes)[0]
                full_step_rows = list(first_ep.get("transitions", []) or [])
            if not full_step_rows:
                full_step_rows = list(getattr(selected_row, "eval_decision_steps_top", []) or [])

            write_eval_bundle_v2(
                out_root=run_root,
                eval_id=eval_id,
                model_id=model_id,
                run_id=run_id,
                scenario_id=str(scenario_id),
                eval_decision_steps_top=full_step_rows,
                eval_decisions_top=list(getattr(selected_row, "eval_decisions_top", []) or []),
                eval_decision_summary=dict(getattr(selected_row, "eval_decision_summary", {}) or {}),
            )
        else:
            print("[Bench][WARN] no result row selected for eval bundle publication", flush=True)
    except Exception as exc:
        print(f"[Bench][WARN] write_eval_bundle_v2 failed: {exc}", flush=True)


def publish_eval_catalog(
    *,
    repo_root: Path,
    run_id: str,
    publish_eval_run_fn,
) -> None:
    try:
        publish_result = publish_eval_run_fn(
            repo_root=repo_root,
            run_id=str(run_id or ""),
        )
        print(
            "[Bench] catalog_publish="
            f"{str(publish_result.get('publish_status', 'unknown'))} "
            f"status_path={str(publish_result.get('publish_status_path', ''))}",
            flush=True,
        )
    except Exception as exc:
        print(f"[Bench][WARN] catalog publish after eval failed: {exc}", flush=True)
