from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class TrainResult:
    agent_name: str
    run_id: str
    checkpoint_path: str
    metadata: dict


@runtime_checkable
class AgentAdapter(Protocol):
    name: str

    def train(self, *, config_path: str, stage_name: str, scenario_id: str) -> TrainResult:
        ...
