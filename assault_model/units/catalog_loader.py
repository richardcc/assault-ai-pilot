import json
from pathlib import Path
from typing import Dict

from assault_model.units.unit_type import (
    UnitType,
    UnitSide,
    UnitCategory,
)

# DEBUG TRACE (configurable por entorno)
import os
DEBUG_TRACE = os.getenv("ASSAULT_DEBUG_TRACE", "0") == "1"


def _trace(tag: str, **data):
    if not DEBUG_TRACE:
        return
    payload = " ".join(f"{k}={v}" for k, v in data.items())
    print(f"[TRACE][{tag}] {payload}")


class UnitCatalogError(Exception):
    """Raised when the unit catalog is invalid or cannot be loaded."""


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

    # TRACE SALIDA DEL CATALOGO
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