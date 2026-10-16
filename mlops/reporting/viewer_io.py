from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from mlops.reporting.catalog_runtime import (
    load_catalog_payload as _load_catalog_payload_runtime,
    read_catalog as _read_catalog_runtime,
)


def _sanitize_json_value(value: Any) -> Any:
    if isinstance(value, float):
        # JSON.parse in browsers rejects NaN/Infinity literals.
        if not math.isfinite(value):
            return None
        return value
    if isinstance(value, dict):
        return {str(k): _sanitize_json_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_json_value(v) for v in value]
    if isinstance(value, tuple):
        return [_sanitize_json_value(v) for v in value]
    return value


def json_bytes(payload: dict) -> bytes:
    safe_payload = _sanitize_json_value(payload if isinstance(payload, dict) else {})
    return json.dumps(safe_payload, indent=2, allow_nan=False).encode("utf-8")


def read_catalog(path: Path) -> dict:
    return _read_catalog_runtime(path)


def load_catalog_payload(repo_root: Path, catalog_rel_path: str) -> dict:
    return _load_catalog_payload_runtime(
        repo_root=repo_root, catalog_rel_path=catalog_rel_path
    )
