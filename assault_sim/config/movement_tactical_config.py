from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MovementTacticalConfig:
    advance_terrain_weight: float = 0.55
    flank_terrain_weight: float = 0.45
    retreat_terrain_weight: float = 0.50


def load_movement_tactical_config(path: Path | None = None) -> MovementTacticalConfig:
    if path is None:
        repo_root = Path(__file__).resolve().parents[2]
        path = repo_root / "assault_sim" / "config" / "movement_tactical_config.json"
    if not path.exists():
        return MovementTacticalConfig()
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    base = MovementTacticalConfig()
    return MovementTacticalConfig(
        advance_terrain_weight=float(payload.get("advance_terrain_weight", base.advance_terrain_weight)),
        flank_terrain_weight=float(payload.get("flank_terrain_weight", base.flank_terrain_weight)),
        retreat_terrain_weight=float(payload.get("retreat_terrain_weight", base.retreat_terrain_weight)),
    )

