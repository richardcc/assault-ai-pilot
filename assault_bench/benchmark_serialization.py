from __future__ import annotations

import json
from pathlib import Path


def json_default(value):
    """Best-effort JSON fallback for bench payloads/replays."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): v for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return list(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return to_dict()
        except Exception:
            pass
    as_dict = getattr(value, "__dict__", None)
    if isinstance(as_dict, dict):
        return as_dict
    return str(value)


def json_dumps(payload, *, indent: int | None = None) -> str:
    return json.dumps(payload, ensure_ascii=False, default=json_default, indent=indent)
