from __future__ import annotations

from typing import Dict, List, Optional


def build_unit_index(units: List[object]) -> Dict[str, object]:
    out: Dict[str, object] = {}
    for unit in list(units or []):
        unit_id = str(getattr(unit, "unit_id", "") or "").strip()
        if not unit_id:
            continue
        out[unit_id] = unit
    return out


def build_legal_action_indexes(
    *,
    legal_actions_list: List[str],
    acting_unit_id: str,
    parse_action_target_hex_fn,
) -> dict[str, object]:
    legal_actions_decoded_target_qr: List[Dict[str, object]] = []
    acting_unit_action_catalog: List[Dict[str, object]] = []
    for idx, action_id_item in enumerate(list(legal_actions_list or [])):
        parsed_target = parse_action_target_hex_fn(action_id=action_id_item)
        legal_actions_decoded_target_qr.append(
            {
                "catalog_index": int(idx),
                "action_id": str(action_id_item),
                "target_q": int(parsed_target[0]) if parsed_target is not None else None,
                "target_r": int(parsed_target[1]) if parsed_target is not None else None,
            }
        )
        parts = str(action_id_item).split(":")
        action_unit_id = parts[1] if len(parts) > 1 else ""
        if str(action_unit_id) == str(acting_unit_id):
            acting_unit_action_catalog.append(
                {
                    "catalog_index": int(idx),
                    "action_id": str(action_id_item),
                }
            )
    return {
        "legal_actions_decoded_target_qr": legal_actions_decoded_target_qr,
        "acting_unit_action_catalog": acting_unit_action_catalog,
    }


def build_candidate_index(
    candidates: List[Dict[str, object]],
) -> Dict[str, Dict[str, object]]:
    out: Dict[str, Dict[str, object]] = {}
    for row in list(candidates or []):
        item = dict(row or {})
        action_id = str(item.get("action_id", "") or "")
        if not action_id:
            continue
        out[action_id] = item
    return out


def first_or_by_action(
    *,
    row_by_action: Dict[str, Dict[str, object]],
    action_id: str,
    fallback_rows: List[Dict[str, object]],
) -> Dict[str, object]:
    key = str(action_id or "")
    if key in row_by_action:
        return dict(row_by_action.get(key, {}) or {})
    if list(fallback_rows or []):
        return dict((fallback_rows or [])[0] or {})
    return {}
