from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_REPLAY_JSON_CACHE: dict[str, dict[str, Any]] = {}
_REPLAY_JSON_CACHE_MAX = 6
_REPLAY_LOG_LINES_CACHE: dict[str, dict[str, Any]] = {}
_REPLAY_LOG_LINES_CACHE_MAX = 12


def read_replay_json_cached(path: Path) -> dict[str, Any]:
    p = path.resolve()
    # Prefer binary .msgpack sidecar when available and up-to-date for fast <5ms loading
    mp_sidecar = p.with_suffix(".msgpack") if p.suffix.lower() == ".json" else p
    target_p = p
    if p.suffix.lower() in {".msgpack", ".mpk"}:
        target_p = p
    elif mp_sidecar.exists():
        try:
            if not p.exists() or mp_sidecar.stat().st_mtime_ns >= p.stat().st_mtime_ns:
                target_p = mp_sidecar
        except Exception:
            target_p = p

    key = str(target_p)
    try:
        mtime_ns = int(target_p.stat().st_mtime_ns)
    except Exception:
        mtime_ns = 0
    cached = _REPLAY_JSON_CACHE.get(key)
    if cached and int(cached.get("mtime_ns", -1)) == mtime_ns:
        payload = cached.get("payload")
        return dict(payload) if isinstance(payload, dict) else {}
    try:
        if target_p.suffix.lower() in {".msgpack", ".mpk"}:
            from assault_backend.telemetry_codec import decode_msgpack

            parsed = decode_msgpack(target_p.read_bytes())
        else:
            parsed = json.loads(target_p.read_text(encoding="utf-8"))
        payload = parsed if isinstance(parsed, dict) else {}
    except Exception:
        payload = {}
    _REPLAY_JSON_CACHE[key] = {"mtime_ns": mtime_ns, "payload": payload}
    while len(_REPLAY_JSON_CACHE) > _REPLAY_JSON_CACHE_MAX:
        oldest = next(iter(_REPLAY_JSON_CACHE.keys()))
        _REPLAY_JSON_CACHE.pop(oldest, None)
    return dict(payload)


def write_replay_msgpack_sidecar(json_path: Path, compress_threshold: int = 2048) -> Path:
    """
    Write a compact binary .msgpack sidecar alongside a JSON replay file,
    preserving the JSON file for human offline forensic inspection while
    accelerating MLOps Viewer replay loading by >80% size reduction.
    """
    from assault_backend.telemetry_codec import encode_msgpack

    p = json_path.resolve()
    payload = json.loads(p.read_text(encoding="utf-8"))
    sidecar = p.with_suffix(".msgpack")
    sidecar.write_bytes(encode_msgpack(payload, compress_threshold=compress_threshold))
    return sidecar


def resolve_replay_path(eval_source_path: str, explicit_replay_path: str = "") -> Path | None:
    replay_raw = str(explicit_replay_path or "").strip()
    if replay_raw:
        p = Path(replay_raw).expanduser().resolve()
        return p if p.exists() else None
    src_raw = str(eval_source_path or "").strip()
    if not src_raw:
        return None
    src = Path(src_raw).expanduser().resolve()
    if not src.exists():
        return None
    parent = src.parent
    name = src.name
    candidates: list[Path] = []
    if name.startswith("bench_eval_"):
        candidates.append(parent / name.replace("bench_eval_", "bench_replay_index_", 1))
    candidates.append(parent / "bench_replay_index_latest.json")
    for c in candidates:
        if c.exists():
            return c.resolve()
    return None


def load_replay_episode_payload(index_path: Path, episode_index: int) -> dict[str, Any]:
    index_payload = read_replay_json_cached(index_path)
    if str(index_payload.get("schema_version", "") or "") != "bench_replay_index_v2":
        return {}
    episodes_meta = list(index_payload.get("episodes_meta", []) or [])
    if not episodes_meta:
        return {}
    idx = max(0, min(int(episode_index), len(episodes_meta) - 1))
    meta = episodes_meta[idx] if isinstance(episodes_meta[idx], dict) else {}
    episode_rel = str(meta.get("episode_path", "") or "").strip()
    if not episode_rel:
        return {}
    episode_path = (index_path.parent / episode_rel).resolve()
    if not episode_path.exists():
        return {}
    episode_payload = read_replay_json_cached(episode_path)
    return dict(episode_payload or {})


def build_replay_log_lines_for_episode(index_path: Path, episode_index: int) -> list[str]:
    p = index_path.resolve()
    key = str(p)
    try:
        mtime_ns = int(p.stat().st_mtime_ns)
    except Exception:
        mtime_ns = 0
    cache_key = key + "::ep=" + str(max(0, int(episode_index)))
    cached = _REPLAY_LOG_LINES_CACHE.get(cache_key)
    if cached and int(cached.get("mtime_ns", -1)) == mtime_ns:
        return list(cached.get("lines", []) or [])

    selected = load_replay_episode_payload(p, int(episode_index))
    transitions = list((selected or {}).get("transitions", []) or [])
    lines: list[str] = []
    for i, tr in enumerate(transitions):
        row = dict(tr or {})
        turn_pre = int(row.get("game_turn", row.get("turn", 0)) or 0)
        turn_post = int(row.get("turn", turn_pre) or turn_pre)
        to_play = str(row.get("to_play", "") or "")
        action_id = str(row.get("action_id", "") or "")
        reward = float(row.get("reward", 0.0) or 0.0)
        dmg = float(row.get("damage_dealt", 0.0) or 0.0)
        kills = int(row.get("kills_dealt", 0) or 0)
        turn_suffix = ""
        if turn_post != turn_pre:
            turn_suffix = f" turn_closed->{turn_post}"
        lines.append(
            f"  step={i} turn={turn_pre}{turn_suffix} to_play={to_play} action={action_id} "
            f"reward={reward:.4f} dmg={dmg:.3f} kills={kills}"
        )
    _REPLAY_LOG_LINES_CACHE[cache_key] = {"mtime_ns": mtime_ns, "lines": lines}
    while len(_REPLAY_LOG_LINES_CACHE) > _REPLAY_LOG_LINES_CACHE_MAX:
        oldest = next(iter(_REPLAY_LOG_LINES_CACHE.keys()))
        _REPLAY_LOG_LINES_CACHE.pop(oldest, None)
    return list(lines)
