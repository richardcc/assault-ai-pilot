from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CurriculumStage:
    name: str
    scenario_id: str
    seeds: list[int]
    train_iterations: int
    eval_episodes: int
    promotion_criteria: dict[str, Any] = field(default_factory=dict)
    train_agents: list[str] = field(default_factory=lambda: ["muzero"])
    muzero_config: str = ""
    benchmark_config: str = ""


@dataclass(frozen=True)
class CurriculumSpec:
    stages: list[CurriculumStage]


@dataclass(frozen=True)
class ExperimentPaths:
    run_root: Path
    benchmark_config: Path
    muzero_config: Path
    curriculum_config: Path


@dataclass(frozen=True)
class ExperimentConfig:
    experiment_name: str
    agents: list[str]
    paths: ExperimentPaths
    execution: dict[str, Any] = field(default_factory=dict)
