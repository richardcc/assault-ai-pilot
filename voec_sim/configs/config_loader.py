from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from voec_sim.assets_bridge.importers import AssetPaths


@dataclass(frozen=True)
class VOECConfig:
    assets: AssetPaths
    default_scenario_id: str


def load_voec_config(path: Path) -> VOECConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assets_raw = raw.get("assets", {})
    defaults = raw.get("defaults", {})
    assets = AssetPaths(
        root=Path(assets_raw.get("root", "assault_sim/assets")),
        unit_catalog=Path(assets_raw.get("unit_catalog", "catalogs/unit_catalog.json")),
        map_piece_catalog=Path(
            assets_raw.get("map_piece_catalog", "catalogs/map_piece_catalog.json")
        ),
        scenarios_dir=Path(assets_raw.get("scenarios_dir", "scenarios")),
    )
    return VOECConfig(
        assets=assets,
        default_scenario_id=str(defaults.get("scenario_id", "battaglia_cittadina_2_1")),
    )
