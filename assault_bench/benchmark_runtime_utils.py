from __future__ import annotations

import re
from pathlib import Path
from typing import Dict


def resolve_bench_device(device_cfg: str) -> str:
    import torch

    raw = str(device_cfg or "cuda").strip().lower()
    if raw == "cpu":
        return "cpu"
    if raw == "cuda":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if raw == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    return "cpu"


def resolve_bench_device_choice(config_device_cfg: str, cli_device: str = "") -> str:
    raw_cli = str(cli_device or "").strip().lower()
    if raw_cli in {"cpu", "cuda", "auto"}:
        return resolve_bench_device(raw_cli)
    return resolve_bench_device(str(config_device_cfg or "auto"))


def resolve_enabled_profiles(benchmark_cfg: Dict[str, object]) -> set[str]:
    default_profiles = {
        "muzero_selfplay",
        "muzero_vs_random_side_a",
        "muzero_vs_random_side_b",
    }
    # Backward compatible: old configs used enabled_profiles.
    raw = benchmark_cfg.get("matchup_profiles", None)
    if raw is None:
        raw = benchmark_cfg.get("enabled_profiles", None)
    if raw is None:
        return set(default_profiles)
    configured = {
        str(x or "").strip().lower()
        for x in list(raw or [])
        if str(x or "").strip()
    }
    # Accept legacy aliases from earlier refactor iterations.
    aliases = {
        "selfplay": "muzero_selfplay",
        "vs_random_side_a": "muzero_vs_random_side_a",
        "vs_random_side_b": "muzero_vs_random_side_b",
    }
    normalized = {aliases.get(v, v) for v in configured}
    return normalized or set(default_profiles)


def iter_index_from_checkpoint_name(name: str) -> int:
    m = re.search(r"iter_(\d+)\.pt$", str(name))
    return int(m.group(1)) if m else -1


def resolve_checkpoint_path(checkpoint_path: str, run_root: Path) -> str:
    raw = str(checkpoint_path or "").strip()
    if raw and raw.lower() != "latest":
        return raw
    ckpts = list(run_root.glob("muzero_*/checkpoints/iter_*.pt"))
    ckpts.extend(list(run_root.glob("efficientzero_v2_*/checkpoints/iter_*.pt")))
    ckpts.extend(list(run_root.glob("efficientzero_v2_*/checkpoints/final.pt")))
    if not ckpts:
        return ""
    best = sorted(
        ckpts,
        key=lambda p: (p.stat().st_mtime, iter_index_from_checkpoint_name(p.name)),
        reverse=True,
    )[0]
    return str(best)


def engine_kind_from_checkpoint_path(checkpoint_path: str) -> str:
    raw = str(checkpoint_path or "").strip().replace("\\", "/")
    if not raw:
        return "muzero"
    parts = [p for p in raw.split("/") if p]
    for part in parts:
        if str(part).startswith("efficientzero_v2_"):
            return "efficientzero_v2"
        if str(part).startswith("muzero_"):
            return "muzero"
    return "muzero"


def resolve_repo_root_from(start_path: str | Path) -> Path:
    start = Path(start_path).resolve()
    for p in [start] + list(start.parents):
        if (p / ".git").exists():
            return p
    return Path.cwd().resolve()
