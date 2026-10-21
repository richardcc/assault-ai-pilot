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


def build_efficientzero_v2_replay_payload(
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


def _enrich_episodes_meta(rp: Path, raw_meta: list[dict[str, Any]]) -> list[dict[str, Any]]:
    import json

    cache_file = rp.parent / f".cache_meta_{rp.stem}.json"
    if cache_file.exists():
        try:
            cached_data = json.loads(cache_file.read_text(encoding="utf-8"))
            if isinstance(cached_data, list) and len(cached_data) == len(raw_meta):
                return cached_data
        except Exception:
            pass

    enriched: list[dict[str, Any]] = []
    for idx, ep in enumerate(raw_meta):
        if not isinstance(ep, dict):
            continue
        ep_idx = idx
        raw_ep_num = int(ep.get("episode_index", idx) or idx)
        seed = int(ep.get("seed", 0) or 0)
        agent_name = str(ep.get("agent_name", "") or "")
        trans_count = int(ep.get("transitions", 0) or ep.get("rows", 0) or 0)
        ep_path = str(ep.get("episode_path", "") or "")

        sid = str(ep.get("scenario_id", "") or "")
        if sid.startswith("multi:"):
            sid = ""
        winner = str(ep.get("winner", "") or "")
        outcome = str(ep.get("outcome", "") or "")

        matchup = "selfplay"
        matchup_label = "Self-Play (MCTS vs MCTS)"
        an_lower = agent_name.lower()
        if "random_us" in an_lower or "side_b" in an_lower:
            matchup = "mcts_vs_random_def"
            matchup_label = "MCTS Defensor vs Random Atacante (US)"
        elif "random_it" in an_lower or "random_ge" in an_lower or "side_a" in an_lower:
            matchup = "mcts_vs_random_atk"
            matchup_label = "MCTS Atacante vs Random Defensor (Eje)"
        elif "random" in an_lower:
            matchup = "vs_random"
            matchup_label = "MCTS vs Random"

        full_path = rp.parent / ep_path if ep_path else None
        if full_path and full_path.exists() and (not sid or not winner):
            try:
                ep_data = json.loads(full_path.read_text(encoding="utf-8"))
                if not sid:
                    sid = str(ep_data.get("scenario_id", "") or "")
                if not winner:
                    winner = str(ep_data.get("winner", "") or "")
                if not outcome:
                    outcome = str(ep_data.get("outcome", "") or "")
            except Exception:
                pass

        scenario_name = sid or "Escenario Wargame"

        enriched.append({
            "episode_id": f"episode_{ep_idx}",
            "episode_index": ep_idx,
            "seed": seed,
            "agent_name": agent_name,
            "matchup": matchup,
            "matchup_label": matchup_label,
            "scenario_id": sid,
            "scenario_name": scenario_name,
            "winner": winner,
            "outcome": outcome,
            "rows": trans_count,
            "steps_count": trans_count,
            "episode_path": ep_path,
        })

    try:
        cache_file.write_text(json.dumps(enriched, indent=2), encoding="utf-8")
    except Exception:
        pass

    return enriched


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
                payload["episodes_meta"] = _enrich_episodes_meta(rp, raw_meta)
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


def detect_scenario_id_from_transitions(
    transitions: list[dict[str, Any]],
    repo_root: Path | None = None,
    default_scenario_id: str = "",
) -> str:
    if not transitions:
        return default_scenario_id
    t0 = transitions[0] if isinstance(transitions[0], dict) else {}
    uids = {
        str(u.get("unit_id", "") or "")
        for u in t0.get("units", [])
        if isinstance(u, dict)
    }
    vp_keys = {str(k) for k in (t0.get("vp_map", {}) or {}).keys()}


    if repo_root is not None:
        from assault_model.paths import SCENARIOS_DIR as scenarios_dir
        if scenarios_dir.exists():
            best_sid = default_scenario_id
            best_score = 0
            for p in scenarios_dir.glob("*.json"):
                try:
                    import json

                    raw = json.loads(p.read_text(encoding="utf-8"))
                    scen_units = {
                        str(u.get("unit_id", "")) for u in raw.get("units", [])
                    }
                    scen_vps = {
                        f"{h.get('q')},{h.get('r')}"
                        for h in (raw.get("vp", {}) or {}).get("hexes", [])
                    }
                    score = len(uids & scen_units) * 2 + len(vp_keys & scen_vps) * 3
                    if score > best_score:
                        best_score = score
                        best_sid = str(p.stem)
                except Exception:
                    pass
            if best_score > 0:
                return best_sid

    return default_scenario_id


def build_v2_replay_steps_payload(
    *,
    eval_source_path: str,
    episode_id: str,
    from_step: int,
    to_step: int,
    repo_root: Path | None = None,
    load_scenario_overlay: Callable[[Path, str], dict[str, Any]] | None = None,
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
                if repo_root is not None and load_scenario_overlay is not None:
                    detected_sid = detect_scenario_id_from_transitions(
                        raw_transitions, repo_root, default_scenario_id=str(ep_payload.get("scenario_id", "") or "")
                    )
                    if detected_sid:
                        payload["scenario_id"] = detected_sid
                        payload["scenario_overlay"] = load_scenario_overlay(repo_root, detected_sid)
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
    if repo_root is not None and load_scenario_overlay is not None and payload["steps"]:
        detected_sid = detect_scenario_id_from_transitions(payload["steps"], repo_root)
        if detected_sid:
            payload["scenario_id"] = detected_sid
            payload["scenario_overlay"] = load_scenario_overlay(repo_root, detected_sid)
    return payload
