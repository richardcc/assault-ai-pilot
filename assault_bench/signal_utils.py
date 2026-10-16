from __future__ import annotations

import math
from typing import Any


def safe_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except Exception:
        return None
    return out if math.isfinite(out) else None


def first_non_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None
