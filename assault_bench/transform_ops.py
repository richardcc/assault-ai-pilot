from __future__ import annotations

from functools import reduce
from typing import Callable, Dict, Iterable, List, Optional, Sequence, TypeVar

T = TypeVar("T")
U = TypeVar("U")


def to_dict_rows(rows: Optional[Iterable[object]]) -> List[Dict[str, object]]:
    out: List[Dict[str, object]] = []
    for row in list(rows or []):
        if row is None:
            out.append({})
            continue
        if isinstance(row, dict):
            out.append(dict(row))
            continue
        try:
            out.append(dict(row))
            continue
        except Exception:
            pass
        obj_dict = getattr(row, "__dict__", None)
        if isinstance(obj_dict, dict):
            out.append(dict(obj_dict))
        else:
            out.append({})
    return out


def map_rows(rows: Sequence[T], fn: Callable[[T], U]) -> List[U]:
    return [fn(r) for r in rows]


def filter_rows(rows: Sequence[T], fn: Callable[[T], bool]) -> List[T]:
    return [r for r in rows if fn(r)]


def reduce_rows(rows: Sequence[T], fn: Callable[[U, T], U], initial: U) -> U:
    return reduce(fn, rows, initial)


def index_rows_by_int_key(
    rows: Sequence[Dict[str, object]], *, key: str
) -> Dict[int, Dict[str, object]]:
    out: Dict[int, Dict[str, object]] = {}
    for row in rows:
        try:
            idx = int(row.get(key, 0) or 0)
        except Exception:
            idx = 0
        out[idx] = row
    return out


def collect_numeric_columns(
    rows: Sequence[Dict[str, object]], keys: Sequence[str]
) -> Dict[str, List[float]]:
    columns: Dict[str, List[float]] = {str(k): [] for k in keys}
    for row in rows:
        rr = dict(row or {})
        for key in keys:
            try:
                value = float(rr.get(key, 0.0) or 0.0)
            except Exception:
                value = 0.0
            columns[str(key)].append(float(value))
    return columns

