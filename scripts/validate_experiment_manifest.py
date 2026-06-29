"""
Validate experiment manifest files used by automation/governance tooling.

This script is intentionally standalone (no extra dependencies) so it can run
in any local environment without touching training code paths.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ALLOWED_SURFACES = {"planner", "reward", "guardrail", "architecture", "heuristic", "rag", "automation"}
ALLOWED_STATUS = {"planned", "running", "done_keep", "done_revert", "cancelled"}


def _is_non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_manifest(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    required_top = [
        "experiment_id",
        "description",
        "owner",
        "created_at_utc",
        "baseline",
        "scope",
        "policy",
        "changes",
        "execution",
        "acceptance",
        "status",
    ]
    for key in required_top:
        if key not in data:
            errors.append(f"missing required field: {key}")

    if errors:
        return errors

    if not _is_non_empty_str(data["experiment_id"]):
        errors.append("experiment_id must be a non-empty string")
    if not _is_non_empty_str(data["description"]):
        errors.append("description must be a non-empty string")
    if not _is_non_empty_str(data["owner"]):
        errors.append("owner must be a non-empty string")
    if not _is_non_empty_str(data["created_at_utc"]):
        errors.append("created_at_utc must be a non-empty UTC timestamp string")

    baseline = data.get("baseline")
    if not isinstance(baseline, dict):
        errors.append("baseline must be an object")
    else:
        report_paths = baseline.get("report_paths")
        if not isinstance(report_paths, list) or not report_paths:
            errors.append("baseline.report_paths must be a non-empty list")
        else:
            for i, p in enumerate(report_paths):
                if not _is_non_empty_str(p):
                    errors.append(f"baseline.report_paths[{i}] must be a non-empty string")

    scope = data.get("scope")
    if not isinstance(scope, dict):
        errors.append("scope must be an object")
    else:
        if not _is_non_empty_str(scope.get("side")):
            errors.append("scope.side must be a non-empty string")
        if not _is_non_empty_str(scope.get("scenario")):
            errors.append("scope.scenario must be a non-empty string")
        seeds = scope.get("seeds")
        if not isinstance(seeds, list) or not seeds:
            errors.append("scope.seeds must be a non-empty list")
        else:
            for i, seed in enumerate(seeds):
                if not isinstance(seed, int):
                    errors.append(f"scope.seeds[{i}] must be an integer")
        episodes = scope.get("episodes")
        if not isinstance(episodes, int) or episodes <= 0:
            errors.append("scope.episodes must be a positive integer")

    policy = data.get("policy")
    if not isinstance(policy, dict):
        errors.append("policy must be an object")
    else:
        if not isinstance(policy.get("single_lever_only"), bool):
            errors.append("policy.single_lever_only must be a boolean")
        mixed = policy.get("forbidden_mixed_surfaces")
        if mixed is not None:
            if not isinstance(mixed, list):
                errors.append("policy.forbidden_mixed_surfaces must be a list")
            else:
                for i, s in enumerate(mixed):
                    if not _is_non_empty_str(s):
                        errors.append(f"policy.forbidden_mixed_surfaces[{i}] must be a non-empty string")

    changes = data.get("changes")
    if not isinstance(changes, list) or not changes:
        errors.append("changes must be a non-empty list")
    else:
        used_surfaces: set[str] = set()
        for i, c in enumerate(changes):
            if not isinstance(c, dict):
                errors.append(f"changes[{i}] must be an object")
                continue
            surface = c.get("surface")
            if not _is_non_empty_str(surface):
                errors.append(f"changes[{i}].surface must be a non-empty string")
            else:
                s = str(surface).strip().lower()
                if s not in ALLOWED_SURFACES:
                    errors.append(f"changes[{i}].surface '{surface}' is not allowed")
                used_surfaces.add(s)
            if not _is_non_empty_str(c.get("file")):
                errors.append(f"changes[{i}].file must be a non-empty string")
            if not _is_non_empty_str(c.get("key")):
                errors.append(f"changes[{i}].key must be a non-empty string")
            if "old" not in c:
                errors.append(f"changes[{i}].old is required")
            if "new" not in c:
                errors.append(f"changes[{i}].new is required")

        single_lever_only = bool((policy or {}).get("single_lever_only"))
        if single_lever_only and len(used_surfaces) > 1:
            errors.append(
                "policy.single_lever_only=true but changes touch multiple surfaces: "
                + ", ".join(sorted(used_surfaces))
            )

    execution = data.get("execution")
    if not isinstance(execution, dict):
        errors.append("execution must be an object")
    else:
        if not _is_non_empty_str(execution.get("train_command")):
            errors.append("execution.train_command must be a non-empty string")
        if not _is_non_empty_str(execution.get("gate_command")):
            errors.append("execution.gate_command must be a non-empty string")

    acceptance = data.get("acceptance")
    if not isinstance(acceptance, dict):
        errors.append("acceptance must be an object")
    else:
        required = acceptance.get("required")
        if not isinstance(required, list) or not required:
            errors.append("acceptance.required must be a non-empty list")
        else:
            for i, rule in enumerate(required):
                if not _is_non_empty_str(rule):
                    errors.append(f"acceptance.required[{i}] must be a non-empty string")

    status = data.get("status")
    if not _is_non_empty_str(status):
        errors.append("status must be a non-empty string")
    else:
        normalized = str(status).strip().lower()
        if normalized not in ALLOWED_STATUS:
            errors.append(
                f"status '{status}' is invalid (allowed: {', '.join(sorted(ALLOWED_STATUS))})"
            )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate experiment manifest JSON.")
    parser.add_argument("manifest", type=Path, help="Path to manifest JSON file")
    args = parser.parse_args()

    manifest_path = args.manifest
    if not manifest_path.exists():
        print(f"ERROR: file does not exist: {manifest_path}")
        return 2

    try:
        # Use utf-8-sig so manifests written by Windows PowerShell
        # (UTF-8 with BOM) are parsed correctly.
        data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON: {exc}")
        return 2
    except OSError as exc:
        print(f"ERROR: cannot read file: {exc}")
        return 2

    if not isinstance(data, dict):
        print("ERROR: manifest root must be an object")
        return 2

    errors = _validate_manifest(data)
    if errors:
        print("INVALID manifest:")
        for e in errors:
            print(f" - {e}")
        return 1

    print("VALID manifest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

