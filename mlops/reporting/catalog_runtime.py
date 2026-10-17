from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_CATALOG_CACHE: dict[str, tuple[float, int, dict[str, Any]]] = {}


def read_catalog(path: Path) -> dict:
    if not path.exists():
        return {
            "schema_version": "reporting_v2_strict",
            "engines": [],
            "error": f"catalog not found: {path}",
        }
    try:
        stat = path.stat()
        mtime = stat.st_mtime
        size = stat.st_size
        cache_key = str(path.resolve())
        cached = _CATALOG_CACHE.get(cache_key)
        if cached and cached[0] == mtime and cached[1] == size:
            return cached[2]

        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            _CATALOG_CACHE[cache_key] = (mtime, size, data)
            return data
        return data
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

