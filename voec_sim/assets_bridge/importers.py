from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from assault_model.map.map_piece_loader import load_map_piece_catalog
from assault_model.units.catalog_loader import load_unit_catalog


DEFAULT_ASSETS_ROOT = Path("assault_sim/assets")
DEFAULT_UNIT_CATALOG = Path("catalogs/unit_catalog.json")
DEFAULT_MAP_PIECES = Path("catalogs/map_piece_catalog.json")
DEFAULT_SCENARIOS_DIR = Path("scenarios")


@dataclass(frozen=True)
class AssetPaths:
    root: Path = DEFAULT_ASSETS_ROOT
    unit_catalog: Path = DEFAULT_UNIT_CATALOG
    map_piece_catalog: Path = DEFAULT_MAP_PIECES
    scenarios_dir: Path = DEFAULT_SCENARIOS_DIR

    @property
    def unit_catalog_path(self) -> Path:
        return self.root / self.unit_catalog

    @property
    def map_piece_catalog_path(self) -> Path:
        return self.root / self.map_piece_catalog

    @property
    def scenarios_path(self) -> Path:
        return self.root / self.scenarios_dir


def _resolve_repo_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    repo_root = Path(__file__).resolve().parents[2]
    return (repo_root / path).resolve()


def load_catalogs(paths: AssetPaths) -> tuple[Dict, Dict]:
    unit_catalog = load_unit_catalog(_resolve_repo_path(paths.unit_catalog_path))
    map_piece_catalog = load_map_piece_catalog(
        _resolve_repo_path(paths.map_piece_catalog_path)
    )
    return unit_catalog, map_piece_catalog


def list_scenario_ids(paths: AssetPaths) -> List[str]:
    scenarios_path = _resolve_repo_path(paths.scenarios_path)
    if not scenarios_path.exists():
        return []
    return sorted(p.stem for p in scenarios_path.glob("*.json"))
