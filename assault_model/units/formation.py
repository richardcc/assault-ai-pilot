"""
assault_model/units/formation.py

Domain model and catalog loader for Tactical Formations (Combined Arms OOB).
Aligns with official wargame rules Section 5.0 and Roadmap Subtask 3.5.2.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from assault_model.paths import FORMATION_CATALOG_PATH, UNIT_CATALOG_PATH


VALID_EXPERIENCE_LEVELS = {"RECRUIT", "REGULAR", "HARDENED", "VETERAN", "ELITE"}


class FormationValidationError(Exception):
    """Raised when a formation configuration violates schema or unit catalog integrity."""
    pass


@dataclass
class Formation:
    """Represents a combined arms military formation card."""
    id: str
    name: str
    side: str
    command_rating: int = 8
    command_points: int = 2
    experience_level: str = "REGULAR"
    experience_units_count: int = 0
    line_units: List[str] = field(default_factory=list)
    heavy_weapons: List[str] = field(default_factory=list)
    specialists: List[str] = field(default_factory=list)
    units: List[str] = field(default_factory=list)
    card_image: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        # Standardize side to uppercase
        self.side = self.side.upper().strip()
        self.experience_level = self.experience_level.upper().strip()
        if self.experience_level not in VALID_EXPERIENCE_LEVELS:
            self.experience_level = "REGULAR"
        # If units is empty, compute from the three categorical slots
        if not self.units:
            self.units = list(self.line_units) + list(self.heavy_weapons) + list(self.specialists)
        # Conversely, if categorical slots are empty but units is provided, categorize as line_units
        elif not self.line_units and not self.heavy_weapons and not self.specialists:
            self.line_units = list(self.units)

    @property
    def total_unit_count(self) -> int:
        return len(self.units)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "side": self.side,
            "command_rating": self.command_rating,
            "command_points": self.command_points,
            "experience_level": self.experience_level,
            "experience_units_count": self.experience_units_count,
            "line_units": self.line_units,
            "heavy_weapons": self.heavy_weapons,
            "specialists": self.specialists,
            "units": self.units,
            "card_image": self.card_image,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, formation_id: str, data: Dict[str, Any]) -> Formation:
        name = data.get("name", formation_id.replace("_", " ").title())
        side = data.get("side", "US")
        command_rating = int(data.get("command_rating", 8))
        command_points = int(data.get("command_points", 2))
        experience_level = str(data.get("experience_level", "REGULAR")).upper().strip()
        experience_units_count = int(data.get("experience_units_count", 0))
        line_units = list(data.get("line_units", []))
        heavy_weapons = list(data.get("heavy_weapons", []))
        specialists = list(data.get("specialists", []))
        units = list(data.get("units", []))
        card_image = data.get("card_image", "")
        description = data.get("description", "")

        return cls(
            id=formation_id,
            name=name,
            side=side,
            command_rating=command_rating,
            command_points=command_points,
            experience_level=experience_level,
            experience_units_count=experience_units_count,
            line_units=line_units,
            heavy_weapons=heavy_weapons,
            specialists=specialists,
            units=units,
            card_image=card_image,
            description=description,
        )


def load_formation_catalog(path: Optional[Path] = None) -> Dict[str, Formation]:
    """
    Loads and parses the formation catalog JSON.
    Returns a dictionary mapping formation ID to Formation instance.
    """
    target_path = path or FORMATION_CATALOG_PATH
    if not target_path.exists():
        return {}

    with open(target_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    catalog: Dict[str, Formation] = {}
    for fid, fdef in raw_data.items():
        if fid.startswith("_"):
            continue
        catalog[fid] = Formation.from_dict(fid, fdef)

    return catalog


def save_formation_catalog(formations: Dict[str, Formation], path: Optional[Path] = None) -> None:
    """
    Serializes and saves formations dictionary to JSON catalog.
    """
    target_path = path or FORMATION_CATALOG_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)

    data = {fid: f.to_dict() for fid, f in formations.items()}
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def validate_formation_integrity(
    formation: Formation,
    valid_unit_ids: Optional[set[str]] = None,
) -> None:
    """
    Validates formation constraints:
    - Non-empty ID, name, side
    - Command rating between 1 and 12
    - At least 1 unit in formation
    - All referenced unit IDs exist in unit catalog if valid_unit_ids is provided
    """
    if not formation.id.strip():
        raise FormationValidationError("Formation ID cannot be empty.")
    if not formation.name.strip():
        raise FormationValidationError("Formation name cannot be empty.")
    if formation.side not in {"US", "GE", "UK", "IT"}:
        raise FormationValidationError(f"Invalid formation side: {formation.side}. Must be US, GE, UK, or IT.")
    if not (1 <= formation.command_rating <= 12):
        raise FormationValidationError(f"Command rating {formation.command_rating} out of valid bounds (1-12).")
    if not (1 <= formation.command_points <= 4):
        raise FormationValidationError(f"Command points {formation.command_points} out of valid bounds (1-4).")
    if formation.experience_level not in VALID_EXPERIENCE_LEVELS:
        raise FormationValidationError(
            f"Invalid experience level: {formation.experience_level}. Must be one of {sorted(VALID_EXPERIENCE_LEVELS)}."
        )
    if formation.experience_units_count < 0:
        raise FormationValidationError(f"Experience units count cannot be negative: {formation.experience_units_count}.")
    if not formation.units:
        raise FormationValidationError(f"Formation '{formation.id}' contains no units.")

    if valid_unit_ids is not None:
        normalized_valid = {u.upper() for u in valid_unit_ids}
        for uid in formation.units:
            if uid.upper() not in normalized_valid:
                raise FormationValidationError(
                    f"Unit ID '{uid}' in formation '{formation.id}' not found in unit catalog."
                )
