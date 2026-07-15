from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from agents.muzero.train.train_muzero import run_training

from mlops.registry.base import AgentAdapter, TrainResult


def _latest_checkpoint_from_run(run_root: Path, run_id: str) -> str:
    ckpt_dir = run_root / run_id / "checkpoints"
    ckpts = sorted(ckpt_dir.glob("iter_*.pt"), key=lambda p: p.stat().st_mtime, reverse=True)
    return str(ckpts[0]) if ckpts else ""


@dataclass
class MuZeroAdapter:
    run_root: Path
    name: str = "muzero"

    def train(self, *, config_path: str, stage_name: str, scenario_id: str) -> TrainResult:
        out = run_training(config_path=config_path)
        run_id = str(out.get("run_id", "")).strip()
        checkpoint = _latest_checkpoint_from_run(self.run_root, run_id)
        return TrainResult(
            agent_name=self.name,
            run_id=run_id,
            checkpoint_path=checkpoint,
            metadata={
                "stage_name": stage_name,
                "scenario_id": scenario_id,
                "metrics": dict(out.get("metrics", {}) or {}),
            },
        )


@dataclass
class BaselineRandomAdapter:
    name: str = "baseline_random"

    def train(self, *, config_path: str, stage_name: str, scenario_id: str) -> TrainResult:
        return TrainResult(
            agent_name=self.name,
            run_id="baseline_random",
            checkpoint_path="",
            metadata={"stage_name": stage_name, "scenario_id": scenario_id, "note": "No training required"},
        )


def build_default_registry(run_root: Path) -> dict[str, AgentAdapter]:
    return {
        "muzero": MuZeroAdapter(run_root=run_root),
        "baseline_random": BaselineRandomAdapter(),
    }


def get_adapter(registry: dict[str, AgentAdapter], agent_name: str) -> Optional[AgentAdapter]:
    return registry.get(agent_name)
