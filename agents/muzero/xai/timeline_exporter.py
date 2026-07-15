from __future__ import annotations

import argparse
import json
from pathlib import Path

from voec_sim.ui_contract.events import SCHEMA_VERSION


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_transition_rows(run_dir: Path) -> list[dict]:
    events_path = run_dir / "events" / "train_events.jsonl"
    if not events_path.exists():
        raise FileNotFoundError(f"missing events file: {events_path}")
    rows: list[dict] = []
    with events_path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            s = line.strip()
            if not s:
                continue
            try:
                evt = json.loads(s)
            except Exception:
                continue
            if str(evt.get("type", "")) != "TransitionEvent":
                continue
            payload = evt.get("payload", {}) or {}
            rows.append(payload)
    return rows


def _select_episode_keys(
    rows: list[dict],
    iteration: int | None,
    episode: int | None,
) -> tuple[int, int]:
    keys = {
        (int(r.get("iteration", 0)), int(r.get("episode", 0)))
        for r in rows
    }
    if not keys:
        raise ValueError("no TransitionEvent rows in train_events.jsonl")
    if iteration is None and episode is None:
        return sorted(keys)[-1]
    if iteration is None or episode is None:
        raise ValueError("iteration and episode must both be provided")
    key = (int(iteration), int(episode))
    if key not in keys:
        raise ValueError(f"episode not found in events: iteration={iteration}, episode={episode}")
    return key


def _to_int(value, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return int(default)
        return int(value)
    except Exception:
        return int(default)


def _to_float(value, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _to_int_or_none(value):
    try:
        if value is None or value == "":
            return None
        return int(value)
    except Exception:
        return None


def _json_safe(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    # Common runtime coordinate objects
    if hasattr(value, "q") and hasattr(value, "r"):
        try:
            return {"q": int(getattr(value, "q")), "r": int(getattr(value, "r"))}
        except Exception:
            return {"q": str(getattr(value, "q")), "r": str(getattr(value, "r"))}
    if hasattr(value, "name"):
        try:
            return str(getattr(value, "name"))
        except Exception:
            pass
    return str(value)


def _intent_projection(transition_info: dict) -> dict:
    ti = dict(transition_info or {})
    return {
        "plan_intent": str(ti.get("plan_intent", "") or ""),
        "plan_focus_vp_id": str(ti.get("plan_focus_vp_id", "") or ""),
        "plan_team_focus_vp_id": str(ti.get("plan_team_focus_vp_id", "") or ""),
        "intent_alignment_stub": _to_float(ti.get("intent_alignment_stub", 0.0), 0.0),
        "legal_capture_options": _to_int(ti.get("legal_capture_options", 0), 0),
        "objective_had_opportunity": _to_int(ti.get("objective_had_opportunity", 0), 0),
        "objective_distance_before": _to_float(ti.get("objective_distance_before", -1.0), -1.0),
        "objective_distance_after": _to_float(ti.get("objective_distance_after", -1.0), -1.0),
        "objective_min_dist_before": _to_float(ti.get("objective_min_dist_before", ti.get("objective_distance_before", -1.0)), -1.0),
        "objective_min_dist_after": _to_float(ti.get("objective_min_dist_after", ti.get("objective_distance_after", -1.0)), -1.0),
        "objective_progress_delta": _to_float(ti.get("objective_progress_delta", 0.0), 0.0),
        "objective_converted": _to_int(ti.get("objective_converted", 0), 0),
        "objective_best_vp_id": str(ti.get("objective_best_vp_id", "") or ""),
        "vp_distance_vector": _json_safe(dict(ti.get("vp_distance_vector", {}) or {})),
        "vp_distance_vector_size": _to_int(ti.get("vp_distance_vector_size", 0), 0),
        "objective_signal_definition_version": str(ti.get("objective_signal_definition_version", "") or ""),
        "legal_action_count": _to_int_or_none(ti.get("legal_action_count", None)),
        "legal_action_types": [str(x) for x in (ti.get("legal_action_types", []) or [])],
        "policy_top_action": str(ti.get("policy_top_action", "") or ""),
        "mcts_chosen_action": str(ti.get("mcts_chosen_action", "") or ""),
        "policy_overridden_by_mcts": _to_int_or_none(ti.get("policy_overridden_by_mcts", None)),
        "mcts_action_candidates": _json_safe(list(ti.get("mcts_action_candidates", []) or [])),
        "why_action_vs_vp": _json_safe(dict(ti.get("why_action_vs_vp", {}) or {})),
        "why_action_vs_vp_text": str(ti.get("why_action_vs_vp_text", "") or ""),
    }


def export_muzero_episode_timeline(
    repo_root: Path,
    run_id: str,
    iteration: int | None = None,
    episode: int | None = None,
) -> dict:
    runs_root = (repo_root / "runs").resolve()
    run_dir = (runs_root / run_id).resolve()
    try:
        run_dir.relative_to(runs_root)
    except Exception as e:
        raise ValueError("invalid run_id") from e
    if not run_dir.exists() or not run_dir.is_dir():
        raise FileNotFoundError(f"run not found: {run_id}")

    manifest = _read_json(run_dir / "run_manifest.json")
    scenario_id = str(manifest.get("scenario_id", "")).strip()
    seed_base = int(manifest.get("seed", 0))
    if not scenario_id:
        raise ValueError("run_manifest missing scenario_id")

    all_rows = _load_transition_rows(run_dir)
    it_idx, ep_idx = _select_episode_keys(all_rows, iteration=iteration, episode=episode)
    selected = [r for r in all_rows if int(r.get("iteration", 0)) == it_idx and int(r.get("episode", 0)) == ep_idx]
    selected = sorted(selected, key=lambda x: int(x.get("step", 0)))
    scenario_seed = int(seed_base + it_idx + ep_idx)

    transitions: list[dict] = []
    # Log-only export (no simulator re-execution). This preserves recorded actions
    # and avoids replay divergence due to nondeterministic reconstruction.
    for row in selected:
        tr_info = dict(row.get("transition_info", {}) or {})
        intent = _intent_projection(tr_info)
        runtime_events = _json_safe(list(row.get("runtime_events") or tr_info.get("runtime_events", []) or []))
        dice_rolls = list(
            row.get("dice_rolls")
            or row.get("attack_rolls")
            or row.get("combat_rolls")
            or []
        )
        if not dice_rolls:
            for evt in runtime_events:
                if str((dict(evt or {})).get("type", "")) != "ACTION_EFFECT":
                    continue
                payload_evt = dict((dict(evt or {})).get("payload", {}) or {})
                attacker = str(payload_evt.get("attacker", "")).strip()
                if attacker and attacker != str(row.get("unit_id", "")).strip():
                    continue
                for d in list(payload_evt.get("attacker_attack_dice", []) or []):
                    dd = dict(d or {})
                    dice_rolls.append(
                        {
                            "side": "attack",
                            "color": str(dd.get("color", "")),
                            "faces": [str(x) for x in (list(dd.get("faces", []) or []))],
                        }
                    )
                for d in list(payload_evt.get("defender_defense_dice", []) or []):
                    dd = dict(d or {})
                    dice_rolls.append(
                        {
                            "side": "defense",
                            "color": str(dd.get("color", "")),
                            "faces": [str(x) for x in (list(dd.get("faces", []) or []))],
                        }
                    )
        step = _to_int(row.get("step", 0), 0)
        turn = _to_int(row.get("turn", row.get("game_turn", step)), step)
        action_id = str(row.get("action_id", ""))
        transitions.append(
            {
                "schema_version": SCHEMA_VERSION,
                "step": step,
                "game_turn": _to_int(row.get("game_turn", 0), 0),
                "turn": turn,
                "to_play": row.get("to_play", None),
                "requested_action_id": action_id,
                "action_id": action_id,
                "action_mismatch": False,
                "action_kind": str(row.get("action_kind", "")),
                "unit_id": str(row.get("unit_id", "")),
                "unit_side": str(row.get("unit_side", "")),
                "unit_label": str(row.get("unit_label", "")),
                "reward": _to_float(row.get("reward_target", 0.0), 0.0),
                "done": bool(row.get("done", False)),
                "damage_dealt": _to_float(row.get("damage_dealt", 0.0), 0.0),
                "kills_dealt": _to_int(row.get("kills_dealt", 0), 0),
                "attack_target_unit_id": str(row.get("attack_target_unit_id", "")),
                "target_q": _to_int(row.get("target_q", 0), 0),
                "target_r": _to_int(row.get("target_r", 0), 0),
                "attack_distance_mean": _to_float(row.get("attack_distance_mean", -1.0), -1.0),
                "attack_target_cover_mean": _to_float(row.get("attack_target_cover_mean", -1.0), -1.0),
                "attack_target_los_block_mean": _to_float(row.get("attack_target_los_block_mean", -1.0), -1.0),
                "dice_rolls": list(dice_rolls),
                "runtime_events": _json_safe(runtime_events),
                "plan_intent": intent["plan_intent"],
                "plan_focus_vp_id": intent["plan_focus_vp_id"],
                "plan_team_focus_vp_id": intent["plan_team_focus_vp_id"],
                "intent_alignment_stub": intent["intent_alignment_stub"],
                "legal_capture_options": intent["legal_capture_options"],
                "objective_had_opportunity": intent["objective_had_opportunity"],
                "objective_distance_before": intent["objective_distance_before"],
                "objective_distance_after": intent["objective_distance_after"],
                "objective_min_dist_before": intent["objective_min_dist_before"],
                "objective_min_dist_after": intent["objective_min_dist_after"],
                "objective_progress_delta": intent["objective_progress_delta"],
                "objective_converted": intent["objective_converted"],
                "objective_best_vp_id": intent["objective_best_vp_id"],
                "vp_distance_vector": intent["vp_distance_vector"],
                "vp_distance_vector_size": intent["vp_distance_vector_size"],
                "objective_signal_definition_version": intent["objective_signal_definition_version"],
                "legal_action_count": (
                    intent["legal_action_count"]
                    if intent["legal_action_count"] is not None
                    else _to_int_or_none(row.get("legal_action_count", None))
                ),
                "legal_action_types": (
                    list(intent["legal_action_types"])
                    if intent["legal_action_types"]
                    else [str(x) for x in (row.get("legal_action_types", []) or [])]
                ),
                "policy_top_action": (
                    str(intent["policy_top_action"])
                    if intent["policy_top_action"]
                    else str(row.get("policy_top_action", ""))
                ),
                "mcts_chosen_action": (
                    str(intent["mcts_chosen_action"])
                    if intent["mcts_chosen_action"]
                    else str(row.get("mcts_chosen_action", row.get("action_id", "")))
                ),
                "policy_overridden_by_mcts": (
                    intent["policy_overridden_by_mcts"]
                    if intent["policy_overridden_by_mcts"] is not None
                    else _to_int_or_none(row.get("policy_overridden_by_mcts", None))
                ),
                "chosen_action_prob": _to_float(row.get("chosen_action_prob", 0.0), 0.0),
                "mcts_entropy": _to_float(row.get("mcts_entropy", 0.0), 0.0),
                "mcts_margin": _to_float(row.get("mcts_margin", 0.0), 0.0),
                "mcts_total_visits": _to_int(row.get("mcts_total_visits", 0), 0),
                "mcts_active_actions": _to_int(row.get("mcts_active_actions", 0), 0),
                "predicted_value_root": _to_float(row.get("predicted_value_root", 0.0), 0.0),
                "dynamics_pred_reward": _to_float(row.get("dynamics_pred_reward", 0.0), 0.0),
                "dynamics_next_latent_l2": _to_float(row.get("dynamics_next_latent_l2", 0.0), 0.0),
                "dynamics_delta_l2": _to_float(row.get("dynamics_delta_l2", 0.0), 0.0),
                "policy_top_actions": [str(x) for x in (row.get("policy_top_actions", []) or [])],
                "policy_top_probs": [float(x) for x in (row.get("policy_top_probs", []) or [])],
                "mcts_action_candidates": (
                    list(intent["mcts_action_candidates"])
                    if intent["mcts_action_candidates"]
                    else _json_safe(list(row.get("mcts_action_candidates", []) or []))
                ),
                "why_action_vs_vp": (
                    dict(intent["why_action_vs_vp"])
                    if intent["why_action_vs_vp"]
                    else _json_safe(dict(row.get("why_action_vs_vp", {}) or {}))
                ),
                "why_action_vs_vp_text": (
                    str(intent["why_action_vs_vp_text"])
                    if intent["why_action_vs_vp_text"]
                    else str(row.get("why_action_vs_vp_text", ""))
                ),
                "latent_top_indices": [int(x) for x in (row.get("latent_top_indices", []) or [])],
                "latent_top_values": [float(x) for x in (row.get("latent_top_values", []) or [])],
                "latent_l2_norm": _to_float(row.get("latent_l2_norm", 0.0), 0.0),
                "units": list(row.get("units_snapshot", row.get("units", [])) or []),
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "scenario_id": scenario_id,
        "seed": scenario_seed,
        "transitions": transitions,
        "meta": {
            "source": "muzero_train_events_log_only",
            "run_id": run_id,
            "iteration": it_idx,
            "episode": ep_idx,
            "requested_transitions": len(selected),
            "exported_transitions": len(transitions),
            "action_mismatch_count": 0,
            "replay_exact": True,
            "replay_stopped_on_mismatch": False,
            "note": "log_only_timeline_no_resimulation",
        },
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export MuZero episode to VOEC timeline JSON.")
    parser.add_argument("--repo", default=".", help="Repository root path.")
    parser.add_argument("--run-id", required=True, help="MuZero run id, e.g. muzero_ab12cd34.")
    parser.add_argument("--iteration", type=int, default=-1, help="Iteration index (optional with --episode).")
    parser.add_argument("--episode", type=int, default=-1, help="Episode index (optional with --iteration).")
    parser.add_argument("--out", default="", help="Output JSON path. Default: runs/<run_id>/xai/muzero_timeline_latest.json")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    repo_root = Path(args.repo).resolve()
    run_id = str(args.run_id).strip()
    iteration = None if int(args.iteration) < 0 else int(args.iteration)
    episode = None if int(args.episode) < 0 else int(args.episode)
    payload = export_muzero_episode_timeline(
        repo_root=repo_root,
        run_id=run_id,
        iteration=iteration,
        episode=episode,
    )

    default_out = repo_root / "runs" / run_id / "xai" / "muzero_timeline_latest.json"
    out_path = Path(args.out).resolve() if str(args.out).strip() else default_out.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[MuZero] timeline_exported={out_path}")


if __name__ == "__main__":
    main()
