from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Small process-local cache to avoid repeated full-file zstd decompression per chunk request.
_NDJSON_CACHE: dict[str, dict[str, Any]] = {}
_NDJSON_CACHE_MAX_ENTRIES = 8


def eval_root_from_source(eval_source_path: str) -> Path | None:
    src_raw = str(eval_source_path or "").strip()
    if not src_raw:
        return None
    src = Path(src_raw).expanduser().resolve()
    if not src.exists():
        return None
    run_dir = src.parent
    run_id = str(run_dir.name or "").strip()
    # bench_eval files usually live under <runs_root>/<run_id>/xai/bench_eval_*.json
    if run_id.lower() == "xai":
        run_dir = run_dir.parent
        run_id = str(run_dir.name or "").strip()
    if not run_id:
        return None
    out_root = run_dir.parent
    evals_dir = out_root / "evals"
    if not evals_dir.exists():
        return None
    scan_patterns = (f"{run_id}__*", f"{run_id}:*")
    found: list[Path] = []
    for pat in scan_patterns:
        found.extend([p for p in evals_dir.glob(pat) if p.is_dir()])
    candidates = sorted(
        found,
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def read_ndjson_rows(path: Path, start: int, limit: int) -> list[dict]:
    if not path.exists():
        return []
    p = path.resolve()
    key = str(p)
    try:
        mtime_ns = int(p.stat().st_mtime_ns)
    except Exception:
        mtime_ns = 0

    cached = _NDJSON_CACHE.get(key)
    if cached and int(cached.get("mtime_ns", -1)) == mtime_ns:
        lines = list(cached.get("lines", []) or [])
    else:
        raw = p.read_bytes()
        try:
            import zstandard as zstd  # type: ignore

            text = zstd.ZstdDecompressor().decompress(raw).decode("utf-8", errors="replace")
        except Exception:
            text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        _NDJSON_CACHE[key] = {"mtime_ns": mtime_ns, "lines": lines}
        # Keep a bounded cache size (simple FIFO by insertion order).
        while len(_NDJSON_CACHE) > _NDJSON_CACHE_MAX_ENTRIES:
            oldest_key = next(iter(_NDJSON_CACHE.keys()))
            _NDJSON_CACHE.pop(oldest_key, None)

    s = max(0, int(start))
    e = max(s, min(len(lines), s + max(1, int(limit))))
    out: list[dict] = []
    for ln in lines[s:e]:
        ln = ln.strip()
        if not ln:
            continue
        try:
            obj = json.loads(ln)
        except Exception:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out
