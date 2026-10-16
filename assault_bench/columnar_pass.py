from __future__ import annotations

from typing import Dict, List, Sequence

from assault_bench.transform_ops import collect_numeric_columns, to_dict_rows


def aggregate_columns_mean(rows: Sequence[Dict[str, object]], keys: Sequence[str]) -> Dict[str, float]:
    dict_rows = to_dict_rows(rows)
    if not dict_rows:
        return {str(k): 0.0 for k in keys}
    columns = collect_numeric_columns(dict_rows, keys)
    denom = float(max(1, len(dict_rows)))
    return {
        str(k): float(sum(columns.get(str(k), [])) / denom)
        for k in keys
    }


def aggregate_columns_sum(rows: Sequence[Dict[str, object]], keys: Sequence[str]) -> Dict[str, float]:
    columns = collect_numeric_columns(to_dict_rows(rows), keys)
    return {str(k): float(sum(columns.get(str(k), []))) for k in keys}


def aggregate_columns_weighted_mean(
    rows: Sequence[Dict[str, object]],
    *,
    value_keys: Sequence[str],
    weight_key: str,
) -> Dict[str, float]:
    dict_rows = to_dict_rows(rows)
    if not dict_rows:
        return {str(k): 0.0 for k in value_keys}
    columns = collect_numeric_columns(dict_rows, list(value_keys) + [str(weight_key)])
    weights: List[float] = list(columns.get(str(weight_key), []))
    denom = float(sum(weights))
    if denom <= 0.0:
        return {str(k): 0.0 for k in value_keys}
    out: Dict[str, float] = {}
    for key in value_keys:
        vals = list(columns.get(str(key), []))
        out[str(key)] = float(sum(v * w for v, w in zip(vals, weights)) / denom)
    return out

