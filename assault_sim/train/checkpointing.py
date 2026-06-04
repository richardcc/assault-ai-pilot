from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import torch


def load_model_state(path: Path, device: torch.device) -> tuple[dict[str, Any], dict[str, Any] | None]:
    data = torch.load(path, map_location=device)
    if isinstance(data, dict) and "model_state_dict" in data:
        return data["model_state_dict"], data
    return data, None


def build_checkpoint_payload(
    *,
    policy: torch.nn.Module,
    optimizer: torch.optim.Optimizer | None,
    rollout_idx: int,
    seed: int,
    scenario: str,
    rl_side: str,
    hostname: str,
    sim_config_path: Path,
    env_config_path: Path,
    ppo_config: dict[str, Any],
    train_stats: dict[str, Any],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model_state_dict": policy.state_dict(),
        "meta": {
            "rollout_idx": rollout_idx,
            "timestamp_utc": datetime.utcnow().isoformat() + "Z",
            "seed": seed,
            "scenario": scenario,
            "rl_side": rl_side,
            "hostname": hostname,
            "sim_config_path": str(sim_config_path),
            "env_config_path": str(env_config_path),
            "ppo_config": ppo_config,
            "train_stats": train_stats,
        },
    }
    if optimizer is not None:
        payload["optimizer_state_dict"] = optimizer.state_dict()
    return payload


def save_latest(payload: dict[str, Any], model_dir: Path, latest_name: str = "latest.pt") -> Path:
    model_dir.mkdir(parents=True, exist_ok=True)
    latest_path = model_dir / latest_name
    torch.save(payload, latest_path)
    with open(model_dir / "latest.meta.json", "w", encoding="utf-8") as f:
        json.dump(payload.get("meta", {}), f, indent=2)
    return latest_path


def save_numbered(payload: dict[str, Any], model_dir: Path, step: int, prefix: str = "checkpoint_") -> Path:
    model_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path = model_dir / f"{prefix}{step}.pt"
    torch.save(payload, ckpt_path)
    return ckpt_path

