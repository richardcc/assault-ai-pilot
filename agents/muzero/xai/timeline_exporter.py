from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from voec_sim.configs.config_loader import load_voec_config
from voec_sim.core.simulator import VOECSimulator
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


def _snapshot_units(sim: VOECSimulator) -> list[dict]:
    snap = sim.snapshot()
    return [asdict(u) for u in snap.units]


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

    voec_cfg = load_voec_config((repo_root / "voec_sim" / "configs" / "voec_config.yaml").resolve())
    sim = VOECSimulator(assets=voec_cfg.assets)
    sim.new_episode(scenario_id=scenario_id, seed=scenario_seed)

    transitions: list[dict] = []
    mismatch_count = 0
    for row in selected:
        legal = sim.legal_actions()
        if not legal:
            break
        requested_action = str(row.get("action_id", ""))
        action_id = requested_action if requested_action in legal else legal[0]
        if action_id != requested_action:
            mismatch_count += 1
        tr = sim.step(action_id)
        transitions.append(
            {
                "schema_version": SCHEMA_VERSION,
                "turn": int(tr.state.turn),
                "to_play": tr.state.to_play,
                "action_id": action_id,
                "reward": float(tr.reward),
                "done": bool(tr.done),
                "units": _snapshot_units(sim),
            }
        )
        if tr.done:
            break

    return {
        "schema_version": SCHEMA_VERSION,
        "scenario_id": scenario_id,
        "seed": scenario_seed,
        "transitions": transitions,
        "meta": {
            "source": "muzero_train_events_replay",
            "run_id": run_id,
            "iteration": it_idx,
            "episode": ep_idx,
            "requested_transitions": len(selected),
            "exported_transitions": len(transitions),
            "action_mismatch_count": int(mismatch_count),
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
