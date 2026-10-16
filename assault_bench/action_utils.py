from __future__ import annotations

from typing import List

from assault_bench.transform_ops import filter_rows

def action_kind_from_id(action_id: str) -> str:
    raw = str(action_id or "").strip()
    if not raw:
        return ""
    return raw.split(":", 1)[0].strip().upper()


def action_unit_id_from_id(action_id: str) -> str:
    parts = str(action_id or "").split(":")
    if len(parts) < 2:
        return ""
    return str(parts[1] or "")


def is_capture_like_action_kind(kind: str) -> bool:
    k = str(kind or "").strip().upper()
    if not k:
        return False
    return ("CAPTURE" in k) or ("SEIZE" in k) or ("OCCUPY" in k)


def is_stationary_action_kind(kind: str) -> bool:
    k = str(kind or "").strip().upper()
    if not k:
        return False
    return k in {
        "WAIT",
        "PASS",
        "HOLD",
        "END_TURN",
        "OPPORTUNITY_SKIP",
        "OPPORTUNITY_WAIT",
        "NOOP",
    }


def count_capture_like_actions(legal_actions: List[str]) -> int:
    actions = [str(a or "") for a in list(legal_actions or [])]
    capture_like = filter_rows(
        actions, lambda a: is_capture_like_action_kind(action_kind_from_id(a))
    )
    return int(len(capture_like))
