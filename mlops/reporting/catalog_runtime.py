from __future__ import annotations

import json
from pathlib import Path


def read_catalog(path: Path) -> dict:
    if not path.exists():
        return {
            "schema_version": "reporting_v2_strict",
            "engines": [],
            "error": f"catalog not found: {path}",
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "schema_version": "reporting_v2_strict",
            "engines": [],
            "error": f"failed to parse catalog: {exc}",
        }


def load_catalog_payload(repo_root: Path, catalog_rel_path: str) -> dict:
    catalog_path = (repo_root / str(catalog_rel_path)).resolve()
    payload = read_catalog(catalog_path)
    if not isinstance(payload, dict):
        return {
            "schema_version": "reporting_v2_strict",
            "engines": [],
            "error": "catalog payload is not a JSON object",
        }
    return payload
