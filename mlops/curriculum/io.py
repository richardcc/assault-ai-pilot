from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from mlops.contracts import CurriculumSpec, CurriculumStage


def _require(raw: dict[str, Any], key: str) -> Any:
    if key not in raw:
        raise KeyError(f"Missing required key '{key}'")
    return raw[key]


def load_curriculum_spec(path: Path) -> CurriculumSpec:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    stage_rows = list(payload.get("stages", []) or [])
    if not stage_rows:
        raise ValueError("Curriculum must define at least one stage")
    stages: list[CurriculumStage] = []
    for idx, row in enumerate(stage_rows):
        stage = CurriculumStage(
            name=str(row.get("name", f"stage_{idx+1}")),
            scenario_id=str(_require(row, "scenario_id")),
            seeds=[int(x) for x in list(_require(row, "seeds"))],
            train_iterations=int(row.get("train_iterations", 1)),
            eval_episodes=int(row.get("eval_episodes", len(row.get("seeds", [])) or 1)),
            promotion_criteria=dict(row.get("promotion_criteria", {}) or {}),
            train_agents=[str(x) for x in list(row.get("train_agents", ["muzero"]))],
            muzero_config=str(row.get("muzero_config", "")),
            benchmark_config=str(row.get("benchmark_config", "")),
        )
        stages.append(stage)
    return CurriculumSpec(stages=stages)
