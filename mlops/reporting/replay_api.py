from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from mlops.reporting.replay_runtime import (
    build_replay_log_lines_for_episode,
    load_replay_episode_payload,
    read_replay_json_cached,
    resolve_replay_path,
)
from mlops.reporting.replay_v2 import (
    eval_root_from_source,
    read_ndjson_rows,
)


def build_muzero_replay_payload(
    *,
    repo_root: Path,
    eval_source_path: str,
    replay_path: str,
    episode_index: int,
    full_episode: bool,
    chunk_offset: int,
    chunk_limit: int,
    load_scenario_overlay: Callable[[Path, str], dict[str, Any]],
) -> dict[str, Any]:
    rp = resolve_replay_path(eval_source_path=eval_source_path, explicit_replay_path=replay_path)
    payload: dict[str, Any] = {
        "replay_path": str(rp) if rp is not None else "",
        "episodes_meta": [],
        "transitions": [],
        "transitions_total": 0,
        "transitions_offset": int(chunk_offset),
        "transitions_limit": int(chunk_limit),
        "transitions_has_more": False,
    }
    if rp is None:
        payload["error"] = "replay file not found"
        return payload
    try:
        raw = read_replay_json_cached(rp)
        payload["schema_version"] = str(raw.get("schema_version", "") or "")
        payload["run_id"] = str(raw.get("run_id", "") or "")
        payload["scenario_id"] = str(raw.get("scenario_id", "") or "")
        payload["bench_id"] = str(raw.get("bench_id", "") or "")
        payload["scenario_overlay"] = load_scenario_overlay(
            repo_root,
            str(raw.get("scenario_id", "") or ""),
        )
        if str(raw.get("schema_version", "") or "") != "bench_replay_index_v2":
            payload["error"] = "unsupported replay schema (expected bench_replay_index_v2)"
            return payload
        raw_meta = list(raw.get("episodes_meta", []) or [])
        episodes_meta: list[dict[str, Any]] = [
            {
                "episode_index": int((ep or {}).get("episode_index", idx) or idx),
                "seed": int((ep or {}).get("seed", 0) or 0),
                "agent_name": str((ep or {}).get("agent_name", "") or ""),
                "transitions": int((ep or {}).get("transitions", 0) or 0),
            }
            for idx, ep in enumerate(raw_meta)
            if isinstance(ep, dict)
        ]
        payload["episodes_meta"] = episodes_meta
        if episodes_meta:
            idx = max(0, min(int(episode_index), len(episodes_meta) - 1))
            selected_meta = episodes_meta[idx] if isinstance(episodes_meta[idx], dict) else {}
            selected = load_replay_episode_payload(rp, idx)
            payload["selected_episode_index"] = idx
            payload["selected_seed"] = int(selected_meta.get("seed", 0) or 0)
            payload["selected_agent_name"] = str(selected_meta.get("agent_name", "") or "")
            all_transitions = list((selected or {}).get("transitions", []) or [])
            total = int(len(all_transitions))
            if full_episode:
                start = 0
                end = total
            else:
                start = max(0, min(int(chunk_offset), total))
                end = max(start, min(total, start + int(chunk_limit)))
            payload["transitions_total"] = total
            payload["transitions"] = all_transitions[start:end]
            payload["transitions_has_more"] = False if full_episode else bool(end < total)
    except Exception as exc:
        payload["error"] = f"failed to load replay: {exc}"
    return payload


def build_replay_log_payload(
    *,
    eval_source_path: str,
    replay_path: str,
    episode_index: int,
    upto_step: int,
    full_episode_log: bool,
) -> dict[str, Any]:
    rp = resolve_replay_path(eval_source_path=eval_source_path, explicit_replay_path=replay_path)
    payload: dict[str, Any] = {"lines": [], "replay_path": str(rp) if rp is not None else ""}
    if rp is None:
        payload["error"] = "replay file not found"
        return payload
    try:
        lines = build_replay_log_lines_for_episode(rp, int(episode_index))
        if full_episode_log:
            payload["lines"] = list(lines)
        else:
            end_idx = max(0, min(int(upto_step), max(0, len(lines) - 1)))
            clipped = list(lines[: end_idx + 1])
            if clipped:
                clipped[-1] = (
                    ">>" + str(clipped[-1])[2:]
                    if str(clipped[-1]).startswith("  ")
                    else ">> " + str(clipped[-1])
                )
                payload["lines"] = clipped
    except Exception as exc:
        payload["error"] = f"failed to build replay log: {exc}"
    return payload


def build_v2_replay_meta_payload(
    eval_source_path: str,
    *,
    repo_root: Path | None = None,
    load_scenario_overlay: Callable[[Path, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    eval_root = eval_root_from_source(eval_source_path)
    rp = resolve_replay_path(eval_source_path=eval_source_path)
    payload: dict[str, Any] = {"schema_version": "reporting_v2_strict", "episodes_meta": []}

    # 1. Prefer replay index if available (bench_replay_index_*.json has all episodes & full transitions)
    if rp is not None and rp.exists():
        try:
            raw_index = read_replay_json_cached(rp)
            payload["replay_path"] = str(rp)
            payload["run_id"] = str(raw_index.get("run_id", "") or "")
            payload["scenario_id"] = str(raw_index.get("scenario_id", "") or "")
            payload["bench_id"] = str(raw_index.get("bench_id", "") or "")
            raw_meta = list(raw_index.get("episodes_meta", []) or [])
            if raw_meta:
                payload["episodes_meta"] = [
                    {
                        "episode_id": f"episode_{int(ep.get('episode_index', idx) or idx)}",
                        "episode_index": int(ep.get("episode_index", idx) or idx),
                        "seed": int(ep.get("seed", 0) or 0),
                        "agent_name": str(ep.get("agent_name", "") or ""),
                        "rows": int(ep.get("transitions", 0) or 0),
                        "steps_count": int(ep.get("transitions", 0) or 0),
                        "episode_path": str(ep.get("episode_path", "") or ""),
                    }
                    for idx, ep in enumerate(raw_meta)
                    if isinstance(ep, dict)
                ]
        except Exception:
            pass

    # 2. Check eval bundle manifest if available
    if eval_root is not None:
        manifest_path = eval_root / "eval_manifest.json"
        if manifest_path.exists():
            try:
                import json

                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                payload["manifest"] = manifest if isinstance(manifest, dict) else {}
            except Exception as exc:
                payload["manifest"] = {"error": f"failed to parse manifest: {exc}"}
            if not payload["episodes_meta"]:
                eps = list((payload.get("manifest", {}) or {}).get("episodes", []) or [])
                payload["episodes_meta"] = [
                    {
                        "episode_id": str(ep.get("episode_id", "")),
                        "rows": int(ep.get("rows", 0) or 0),
                        "steps_count": int(ep.get("rows", 0) or 0),
                    }
                    for ep in eps
                    if isinstance(ep, dict)
                ]

    if not payload["episodes_meta"] and eval_root is None and rp is None:
        payload["error"] = "eval bundle or replay index not found"
        return payload

    # 3. Load scenario overlay
    if repo_root is not None and load_scenario_overlay is not None:
        scenario_id = str(
            payload.get("scenario_id", "")
            or (payload.get("manifest", {}) or {}).get("scenario_id", "")
            or ""
        )
        if not scenario_id and eval_source_path:
            try:
                import json

                p = Path(eval_source_path)
                if p.exists() and p.suffix == ".json":
                    raw_eval = json.loads(p.read_text(encoding="utf-8"))
                    scenario_id = str(raw_eval.get("scenario_id", "") or "")
            except Exception:
                pass
        payload["scenario_overlay"] = load_scenario_overlay(repo_root, scenario_id)
    return payload


def build_v2_replay_steps_payload(
    *,
    eval_source_path: str,
    episode_id: str,
    from_step: int,
    to_step: int,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "reporting_v2_strict",
        "episode_id": str(episode_id or "episode_0"),
        "from_step": int(max(0, int(from_step))),
        "to_step": int(max(int(from_step), int(to_step))),
        "steps": [],
    }

    # 1. Prefer full transitions from bench_replay_episodes if replay index is available
    rp = resolve_replay_path(eval_source_path=eval_source_path)
    if rp is not None and rp.exists():
        ep_id_str = str(payload["episode_id"]).strip()
        ep_idx = 0
        if ep_id_str.startswith("episode_"):
            try:
                ep_idx = int(ep_id_str.split("_")[1])
            except Exception:
                ep_idx = 0
        else:
            try:
                ep_idx = int(ep_id_str)
            except Exception:
                ep_idx = 0

        try:
            ep_payload = load_replay_episode_payload(rp, ep_idx)
            raw_transitions = list((ep_payload or {}).get("transitions", []) or [])
            if raw_transitions:
                for i, t in enumerate(raw_transitions):
                    if isinstance(t, dict):
                        t.setdefault("step", i)
                        t.setdefault("episode_id", payload["episode_id"])
                start = int(payload["from_step"])
                end = int(payload["to_step"]) + 1
                payload["steps"] = raw_transitions[start:end]
                payload["count"] = int(len(payload["steps"]))
                payload["total_steps"] = int(len(raw_transitions))
                return payload
        except Exception:
            pass

    # 2. Fall back to ndjson.zst bundle
    eval_root = eval_root_from_source(eval_source_path)
    if eval_root is None:
        payload["error"] = "eval bundle or replay index not found"
        return payload
    ep_path = eval_root / "episodes" / f"{payload['episode_id']}.ndjson.zst"
    limit = int(max(1, (payload["to_step"] - payload["from_step"] + 1)))
    payload["steps"] = read_ndjson_rows(ep_path, int(payload["from_step"]), limit)
    payload["count"] = int(len(payload["steps"]))
    return payload
