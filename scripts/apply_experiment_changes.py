"""
Apply experiment manifest changes in a constrained/safe way.

Scope (intentionally strict):
- Only supports JSON files.
- Only supports top-level key replacement (`changes[].key`).
- Only allows files under an allowlist to avoid arbitrary edits.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ALLOWED_JSON_FILES = {
    "assault_sim/config/reward_config.json",
    "assault_sim/config/train_config.json",
}


def _norm_repo_rel(path: Path, repo_root: Path) -> str:
    rel = path.resolve().relative_to(repo_root.resolve())
    return str(rel).replace("\\", "/")


def _load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _apply_one_change(
    repo_root: Path,
    change: dict[str, Any],
    dry_run: bool,
    force_old_mismatch: bool,
) -> tuple[bool, str]:
    file_field = str(change.get("file", "")).strip()
    key_field = str(change.get("key", "")).strip()
    if not file_field or not key_field:
        return False, "missing file/key"

    target = (repo_root / file_field).resolve()
    try:
        rel_norm = _norm_repo_rel(target, repo_root)
    except Exception:
        return False, f"path outside repo: {file_field}"

    if rel_norm not in ALLOWED_JSON_FILES:
        return False, f"file not allowed: {rel_norm}"
    if not target.exists():
        return False, f"file not found: {rel_norm}"
    if target.suffix.lower() != ".json":
        return False, f"unsupported file type: {rel_norm}"

    try:
        obj = json.loads(target.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return False, f"invalid json in {rel_norm}: {exc}"

    if not isinstance(obj, dict):
        return False, f"json root must be object: {rel_norm}"
    if key_field not in obj:
        return False, f"key not found in {rel_norm}: {key_field}"

    old_expected = change.get("old")
    new_value = change.get("new")
    old_actual = obj.get(key_field)
    if old_expected != old_actual and not force_old_mismatch:
        return False, (
            f"old mismatch for {rel_norm}:{key_field} "
            f"(expected={old_expected!r}, actual={old_actual!r})"
        )
    if old_expected != old_actual and force_old_mismatch:
        mismatch_note = (
            f" (forced despite old mismatch expected={old_expected!r}, actual={old_actual!r})"
        )
    else:
        mismatch_note = ""

    if old_actual == new_value:
        return True, f"no-op {rel_norm}:{key_field} already {new_value!r}{mismatch_note}"

    if dry_run:
        return True, (
            f"dry-run update {rel_norm}:{key_field} {old_actual!r} -> {new_value!r}{mismatch_note}"
        )

    obj[key_field] = new_value
    target.write_text(json.dumps(obj, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return True, f"updated {rel_norm}:{key_field} {old_actual!r} -> {new_value!r}{mismatch_note}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply safe JSON changes from experiment manifest.")
    parser.add_argument("--repo-root", required=True, help="Repository root path")
    parser.add_argument("--manifest", required=True, help="Manifest JSON path")
    parser.add_argument("--dry-run", action="store_true", help="Validate and preview changes only")
    parser.add_argument(
        "--force-old-mismatch",
        action="store_true",
        help="Apply new value even when manifest old != current value",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    manifest_path = Path(args.manifest).resolve()
    if not repo_root.exists():
        print(f"ERROR: repo root does not exist: {repo_root}")
        return 2
    if not manifest_path.exists():
        print(f"ERROR: manifest does not exist: {manifest_path}")
        return 2

    try:
        manifest = _load_manifest(manifest_path)
    except Exception as exc:
        print(f"ERROR: cannot parse manifest: {exc}")
        return 2

    changes = manifest.get("changes", [])
    if not isinstance(changes, list) or not changes:
        print("ERROR: manifest has no changes[]")
        return 2

    ok_count = 0
    fail_count = 0
    for idx, change in enumerate(changes):
        if not isinstance(change, dict):
            print(f"[{idx}] FAIL: change must be object")
            fail_count += 1
            continue
        ok, msg = _apply_one_change(
            repo_root,
            change,
            dry_run=args.dry_run,
            force_old_mismatch=args.force_old_mismatch,
        )
        if ok:
            ok_count += 1
            print(f"[{idx}] OK: {msg}")
        else:
            fail_count += 1
            print(f"[{idx}] FAIL: {msg}")

    print(f"SUMMARY: ok={ok_count} fail={fail_count}")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

