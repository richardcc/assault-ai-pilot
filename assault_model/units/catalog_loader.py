import json
import os
from pathlib import Path
from typing import Dict

from assault_model.units.unit_type import (
    UnitType,
    UnitSide,
    UnitCategory,
)

# -------------------------------------------------
# DEBUG TRACE (controlled via environment variable)
# -------------------------------------------------
DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    """
    Internal debug trace helper for catalog loading.

    Prints structured output only when ASSAULT_DEBUG_TRACE=1.
    """
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


# -------------------------------------------------
# Errors
# -------------------------------------------------
class UnitCatalogError(Exception):
    """
    Raised when the unit catalog is invalid or cannot be loaded.
    """
    pass


# -------------------------------------------------
# Loader
# -------------------------------------------------
def load_unit_catalog(path: Path) -> Dict[str, UnitType]:
    """
    Load a unit type catalog from a JSON file.

    Role:
    - Reads static definitions of UNIT TYPES (not instances).
    - Creates UnitType objects keyed by unit code.

    Guarantees:
    - Returned dictionary contains fully constructed UnitType objects.
    - No runtime or scenario logic is applied here.

    Does NOT:
    - Instantiate units on the map.
    - Apply scenario rules.
    - Create victory points or map elements.

    Parameters:
    - path: Path to the unit catalog JSON file.

    Returns:
    - Dict[str, UnitType] mapping unit code -> UnitType
    """

    # Ensure catalog file exists
    if not path.exists():
        raise UnitCatalogError(f"Unit catalog not found: {path}")

    # Load JSON data safely
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise UnitCatalogError(f"Failed to read unit catalog: {exc}") from exc

    # Basic format validation
    if "units" not in raw:
        raise UnitCatalogError("Invalid catalog format: missing 'units' key")

    catalog: Dict[str, UnitType] = {}

    # Parse each unit type definition
    for code, data in raw["units"].items():
        try:
            unit = UnitType(
                code=code,
                side=UnitSide(data["side"]),
                category=UnitCategory(data["category"]),
                subtype=data.get("subtype", ""),
                classification=data.get("classification", ""),
                cost=int(data.get("cost", 0)),
                movement=int(data.get("movement", 0)),
                max_strength=int(data.get("max_strength", 0)),
                base_defense=data.get("base_defense", {}),
                attack=data.get("attack", {}),
                traits=data.get("traits", []),
            )
        except Exception as exc:
            raise UnitCatalogError(
                f"Invalid unit entry '{code}': {exc}"
            ) from exc

        catalog[code] = unit

    # ---------------------------------------------
    # DEBUG TRACE OUTPUT
    # ---------------------------------------------
    _trace(
        "CATALOG_LOADED",
        unit_count=len(catalog),
        sample_keys=list(catalog.keys())[:3],
    )

    if catalog:
        sample = next(iter(catalog.values()))
        _trace(
            "CATALOG_SAMPLE",
            code=sample.code,
            attack_raw=sample._attack_raw,
            base_defense_raw=sample._base_defense_raw,
        )

    return catalog