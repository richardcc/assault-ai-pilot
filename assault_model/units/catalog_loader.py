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
# DEBUG TRACE
# -------------------------------------------------
DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


# -------------------------------------------------
# Errors
# -------------------------------------------------
class UnitCatalogError(Exception):
    pass


# -------------------------------------------------
# VALIDATION HELPERS
# -------------------------------------------------
def _validate_attack_structure(code: str, attack: dict):
    """
    Ensures attack structure is compatible with engine expectations.
    """

    # ✅ MUST have DIRECT_FIRE
    if "DIRECT_FIRE" not in attack:
        raise UnitCatalogError(
            f"Unit '{code}' is missing DIRECT_FIRE attack definition"
        )

    # ✅ DIRECT_FIRE must have INFANTRY or VEHICLE (or both)
    direct = attack["DIRECT_FIRE"]

    if not any(k in direct for k in ["INFANTRY", "VEHICLE"]):
        raise UnitCatalogError(
            f"Unit '{code}' DIRECT_FIRE must define INFANTRY or VEHICLE"
        )

    # ✅ INDIRECT_FIRE is optional but must be valid if present
    if "INDIRECT_FIRE" in attack:
        indirect = attack["INDIRECT_FIRE"]

        if not isinstance(indirect, dict):
            raise UnitCatalogError(
                f"Unit '{code}' INDIRECT_FIRE must be a dict"
            )


# -------------------------------------------------
# Loader
# -------------------------------------------------
def load_unit_catalog(path: Path) -> Dict[str, UnitType]:

    if not path.exists():
        raise UnitCatalogError(f"Unit catalog not found: {path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise UnitCatalogError(f"Failed to read unit catalog: {exc}") from exc

    if "units" not in raw:
        raise UnitCatalogError("Invalid catalog format: missing 'units' key")

    catalog: Dict[str, UnitType] = {}

    for code, data in raw["units"].items():

        attack_data = data.get("attack", {})

        # ✅ NEW VALIDATION
        _validate_attack_structure(code, attack_data)

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
                attack=attack_data,
                traits=data.get("traits", []),
            )
        except Exception as exc:
            raise UnitCatalogError(
                f"Invalid unit entry '{code}': {exc}"
            ) from exc

        catalog[code] = unit

        # ✅ DEBUG per unit
        _trace(
            "UNIT_LOADED",
            code=code,
            has_indirect="INDIRECT_FIRE" in attack_data,
        )

    # ---------------------------------------------
    # DEBUG SUMMARY
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
            attack_keys=list(sample._attack_raw.keys()),
        )

    return catalog
