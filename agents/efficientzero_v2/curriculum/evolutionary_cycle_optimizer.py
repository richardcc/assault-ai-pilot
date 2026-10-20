"""Evolutionary cycle optimizer for EfficientZero V2 curriculums.

This module analyzes curriculum execution histories, identifies the winning cycle
(C_X) for each phase, promotes the winning parametrization to become the new baseline
(C1) for future runs, and synthesizes adaptive exploration/exploitation variants (C2, C3)
around this new baseline.

Weights are NEVER transferred across clean runs; only hyperparameter intelligence evolves.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        content = path.read_text(encoding="utf-8")
        loaded = yaml.safe_load(content)
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def _save_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _deep_merge(target: dict[str, Any], source: dict[str, Any], exclude_keys: set[str] | None = None) -> dict[str, Any]:
    """Recursively merges source dict into target dict, excluding specific keys."""
    exclude = exclude_keys or set()
    for k, v in (source or {}).items():
        if k in exclude:
            continue
        if isinstance(v, dict) and isinstance(target.get(k), dict):
            _deep_merge(target[k], v, exclude)
        elif isinstance(v, dict):
            cleaned = {ck: cv for ck, cv in v.items() if ck not in exclude}
            if cleaned:
                target[k] = copy.deepcopy(cleaned)
        else:
            target[k] = copy.deepcopy(v)
    return target


def _strip_checkpoints(data: dict[str, Any]) -> dict[str, Any]:
    """Ensures no checkpoint paths exist in training/selfplay configurations."""
    if isinstance(data.get("train"), dict):
        data["train"].pop("resume_checkpoint", None)
        data["train"].pop("checkpoint_path", None)
    if isinstance(data.get("selfplay"), dict):
        data["selfplay"].pop("resume_checkpoint", None)
    return data


def audit_last_curriculum_run(
    repo_root: Path,
    curriculum_name: str | None = None,
    trace_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Reads curriculum_phase_traceability.jsonl and extracts the winning cycle for each phase."""
    if trace_path is None:
        trace_path = repo_root / "runs_curriculum" / "experiments" / "reporting" / "curriculum_phase_traceability.jsonl"
    if not trace_path.exists():
        return []

    lines = trace_path.read_text(encoding="utf-8-sig", errors="ignore").splitlines()
    records: list[dict[str, Any]] = []
    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue
        try:
            row = json.loads(line_str)
            if isinstance(row, dict):
                records.append(row)
        except Exception:
            continue

    if not records:
        return []

    # Filter by curriculum name if specified
    if curriculum_name:
        records = [r for r in records if str(r.get("curriculum_name") or "") == curriculum_name]
        if not records:
            return []

    # Group by (curriculum_name, phase_name)
    phase_records: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in records:
        c_name = str(r.get("curriculum_name") or "")
        p_name = str(r.get("phase_name") or "")
        if not p_name:
            continue
        key = (c_name, p_name)
        phase_records.setdefault(key, []).append(r)

    results: list[dict[str, Any]] = []
    for (c_name, p_name), rows in phase_records.items():
        # Look at the most recent cluster of cycles for this phase
        # Sort by recorded_at_utc descending or keep the last up to 6 cycles
        recent_rows = rows[-6:] if len(rows) > 6 else rows

        winning_cycle = 1
        best_row = recent_rows[-1]
        best_tqs = -1.0
        best_wr = -1.0
        promoted_found = False

        for row in recent_rows:
            dec = str(row.get("promotion_decision") or "")
            tqs = float(row.get("tactical_quality_score") or 0.0)
            gm = row.get("gate_metrics") or {}
            wr = float(gm.get("resolved_non_timeout_win_rate", gm.get("win_rate", 0.0)) or 0.0)
            cycle_iter = int(row.get("cycle_iteration") or 1)

            if dec in ("promote", "promote_best_of_cycles"):
                winning_cycle = cycle_iter
                best_row = row
                best_tqs = tqs
                best_wr = wr
                promoted_found = True
                break

            if not promoted_found:
                if tqs > best_tqs or (abs(tqs - best_tqs) < 1e-4 and wr > best_wr):
                    best_tqs = tqs
                    best_wr = wr
                    winning_cycle = cycle_iter
                    best_row = row

        results.append({
            "curriculum_name": c_name,
            "phase_name": p_name,
            "winning_cycle": winning_cycle,
            "total_cycles_run": len(recent_rows),
            "promotion_decision": best_row.get("promotion_decision", "unknown"),
            "promotion_reason": best_row.get("promotion_reason", ""),
            "tactical_quality_score": best_tqs,
            "win_rate": best_wr,
            "train_run_id": best_row.get("train_run_id", ""),
            "recorded_at_utc": best_row.get("recorded_at_utc", ""),
            "raw_row": best_row,
        })

    return results


def synthesize_adaptive_cycle_overlays(
    base_config: dict[str, Any],
    generation: int,
    winning_cycle: int,
) -> dict[int, dict[str, Any]]:
    """Synthesizes structured C2 (Exploitation) and C3 (Exploration) variants around C1."""
    sp = base_config.get("selfplay") or {}
    rs = sp.get("reward_shaping") or {}
    tr = base_config.get("train") or {}

    # Extract baseline numbers
    curr_reanalysis = float(tr.get("reanalysis_ratio", 0.35))
    curr_updates = int(tr.get("train_updates_per_iter", 10))
    curr_temp = float(sp.get("mcts_temperature", 1.10))
    curr_obj_weight = float(tr.get("objective_loss_weight", 0.20))

    curr_vp_bonus = float(rs.get("vp_capture_bonus_per_hex", 2.50))
    curr_prog_bonus = float(rs.get("objective_progress_bonus_per_hex", 1.80))
    curr_cap_bonus = float(rs.get("capture_bonus", 1.00))
    curr_potential_weight = float(rs.get("vp_potential_weight", 1.00))

    # --- C2: Exploitation & Tactical Convergence ---
    # Finer search, deeper replay, tighter temperature to lock in precise tactical execution
    c2_overlay = {
        "train": {
            "reanalysis_ratio": min(0.65, round(curr_reanalysis + 0.05, 2)),
            "train_updates_per_iter": max(curr_updates, curr_updates + 2),
        },
        "selfplay": {
            "mcts_temperature": max(0.90, round(curr_temp - 0.05, 2)),
            "reward_shaping": {
                "vp_potential_weight": round(curr_potential_weight + 0.10, 2),
            },
        },
    }

    # --- C3: Exploration & Tactical Aggressiveness ---
    # Elevated objective weights and exploration bonus to break through local minima and force VP capture
    c3_overlay = {
        "train": {
            "objective_loss_weight": min(0.65, round(curr_obj_weight + 0.05, 3)),
            "train_updates_per_iter": max(curr_updates + 2, curr_updates + 4),
        },
        "selfplay": {
            "mcts_temperature": min(1.35, round(curr_temp + 0.05, 2)),
            "reward_shaping": {
                "vp_capture_bonus_per_hex": round(curr_vp_bonus * 1.15, 2),
                "objective_progress_bonus_per_hex": round(curr_prog_bonus * 1.15, 2),
                "capture_bonus": round(curr_cap_bonus * 1.10, 2),
                "vp_urgency_lambda": round(float(rs.get("vp_urgency_lambda", 1.2)) + 0.10, 2),
            },
        },
    }

    return {
        1: {
            "strategy": "promoted_baseline",
            "description": f"Generation {generation} Baseline (Promoted from Cycle {winning_cycle} of previous generation).",
            "overlay": {},
        },
        2: {
            "strategy": "adaptive_exploitation",
            "description": "Exploitation and convergence refinement: +5% reanalysis, tighter MCTS temperature, higher potential weight.",
            "overlay": c2_overlay,
        },
        3: {
            "strategy": "adaptive_exploration",
            "description": "Aggressive frontier exploration: +15% VP capture bonuses, higher objective loss weight, expanded exploration.",
            "overlay": c3_overlay,
        },
    }


def evolve_phase_cycles(
    repo_root: Path,
    phase_name: str,
    base_config_path: Path,
    winning_cycle_info: dict[str, Any],
    plan_path: Path | None = None,
    winning_overlay_path: Path | None = None,
) -> dict[str, Any]:
    """Promotes winning cycle parameters to base config (C1) and generates new C2, C3 proposals."""
    if not base_config_path.is_absolute():
        base_config_path = repo_root / base_config_path

    if not base_config_path.exists():
        raise FileNotFoundError(f"Phase base config not found: {base_config_path}")

    base_cfg = _load_yaml(base_config_path)
    winning_cycle = int(winning_cycle_info.get("winning_cycle") or 1)
    curriculum_name = str(winning_cycle_info.get("curriculum_name") or "")

    # Load existing plan if available to track generations
    if plan_path is None:
        plan_path = base_config_path.parent.parent / "cycles" / f"{phase_name}.adaptive_cycles.yaml"

    existing_plan = _load_yaml(plan_path) if plan_path.exists() else {}
    current_generation = int(existing_plan.get("generation") or 1)
    next_generation = current_generation + 1 if winning_cycle > 1 else current_generation

    # If winning cycle had an explicit overlay file, merge it into the base config
    if winning_overlay_path and winning_overlay_path.exists():
        winning_overlay = _load_yaml(winning_overlay_path)
        _deep_merge(base_cfg, winning_overlay, exclude_keys={"base_config", "resume_checkpoint"})

    # Clean out any checkpoint references (Rule: Clean runs must NEVER drag weights across runs)
    _strip_checkpoints(base_cfg)

    # Save the updated base config (New C1)
    _save_yaml(base_config_path, base_cfg)

    # Synthesize C2 and C3 around new C1
    cycle_specs = synthesize_adaptive_cycle_overlays(
        base_config=base_cfg,
        generation=next_generation,
        winning_cycle=winning_cycle,
    )

    history = existing_plan.get("winning_history") or []
    history.append({
        "generation": current_generation,
        "winning_cycle": winning_cycle,
        "promoted_at_utc": datetime.now(timezone.utc).isoformat(),
        "win_rate": winning_cycle_info.get("win_rate"),
        "tactical_quality_score": winning_cycle_info.get("tactical_quality_score"),
        "promotion_decision": winning_cycle_info.get("promotion_decision"),
    })

    adaptive_plan = {
        "schema_version": "adaptive_cycles.v1",
        "curriculum_name": curriculum_name,
        "phase_name": phase_name,
        "generation": next_generation,
        "last_updated_utc": datetime.now(timezone.utc).isoformat(),
        "base_config_path": str(base_config_path.relative_to(repo_root)).replace("\\", "/"),
        "winning_history": history,
        "cycles": cycle_specs,
    }

    _save_yaml(plan_path, adaptive_plan)

    # Persist audit record to curriculum_generation_lineage.jsonl
    lineage_path = repo_root / "runs_curriculum" / "experiments" / "reporting" / "curriculum_generation_lineage.jsonl"
    lineage_path.parent.mkdir(parents=True, exist_ok=True)
    lineage_row = {
        "schema_version": "curriculum_generation_lineage.v1",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "curriculum_name": curriculum_name,
        "phase_name": phase_name,
        "generation": next_generation,
        "winning_cycle": winning_cycle,
        "metrics": {
            "win_rate": winning_cycle_info.get("win_rate"),
            "tactical_quality_score": winning_cycle_info.get("tactical_quality_score"),
        },
        "plan_path": str(plan_path.relative_to(repo_root)).replace("\\", "/"),
    }
    with lineage_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(lineage_row) + "\n")

    return {
        "ok": True,
        "phase_name": phase_name,
        "generation": next_generation,
        "winning_cycle": winning_cycle,
        "base_config_path": str(base_config_path),
        "plan_path": str(plan_path),
        "cycles": cycle_specs,
    }


def analyze_and_evolve_curriculum(
    repo_root: Path,
    curriculum_yaml: Path,
) -> dict[str, Any]:
    """Top-level coordinator: audits last run and evolves all phases in the curriculum."""
    if not curriculum_yaml.is_absolute():
        curriculum_yaml = repo_root / curriculum_yaml

    curr_data = _load_yaml(curriculum_yaml)
    curriculum_name = str(curr_data.get("name") or "")
    phases = curr_data.get("phases") or []

    audit_summary = audit_last_curriculum_run(repo_root=repo_root, curriculum_name=curriculum_name)
    audit_map = {r["phase_name"]: r for r in audit_summary}

    evolved_phases = []
    for phase in phases:
        p_name = str(phase.get("name") or "")
        train_cfg_rel = str(phase.get("train_config") or "")
        if not p_name or not train_cfg_rel:
            continue

        base_cfg_path = repo_root / train_cfg_rel
        if not base_cfg_path.exists():
            continue

        cycle_info = audit_map.get(p_name)
        if not cycle_info:
            # Fallback if phase wasn't in recent trace
            cycle_info = {
                "curriculum_name": curriculum_name,
                "phase_name": p_name,
                "winning_cycle": 1,
                "win_rate": 0.0,
                "tactical_quality_score": 0.0,
                "promotion_decision": "untracked",
            }

        evolve_res = evolve_phase_cycles(
            repo_root=repo_root,
            phase_name=p_name,
            base_config_path=base_cfg_path,
            winning_cycle_info=cycle_info,
        )
        evolved_phases.append(evolve_res)

    return {
        "ok": True,
        "curriculum_name": curriculum_name,
        "curriculum_yaml": str(curriculum_yaml),
        "evolved_phases": evolved_phases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evolutionary cycle optimizer for EfficientZero V2 curriculums.")
    parser.add_argument("--repo-root", default=".", help="Assault repository root.")
    parser.add_argument("--curriculum-yaml", required=True, help="Path to curriculum.yaml.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    curr_yaml = Path(args.curriculum_yaml)
    if not curr_yaml.is_absolute():
        curr_yaml = (repo_root / curr_yaml).resolve()

    res = analyze_and_evolve_curriculum(repo_root=repo_root, curriculum_yaml=curr_yaml)
    print(f"[EvolutionaryOptimizer] Completed evolution for curriculum: {res.get('curriculum_name')}")
    for p in res.get("evolved_phases", []):
        print(f"  * Phase: {p.get('phase_name')} -> Gen {p.get('generation')} (Baseline from Cycle {p.get('winning_cycle')})")


if __name__ == "__main__":
    main()
