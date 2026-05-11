# =================================================
# services/unit_service.py
# Equivalent to map_piece_service.py
# =================================================

import json
from pathlib import Path

UNIT_CATALOG_PATH = (
    Path(__file__)
    .resolve()
    .parents[2]
    / "assault_sim"
    / "assets"
    / "catalogs"
    / "unit_catalog.json"
)

# -------------------------------------------------
# Load full unit catalog
# -------------------------------------------------
def load_unit_catalog_raw() -> dict:
    if not UNIT_CATALOG_PATH.exists():
        raise FileNotFoundError("unit_catalog.json")

    with UNIT_CATALOG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)

# -------------------------------------------------
# Load single unit definition
# -------------------------------------------------
def load_unit_raw(unit_key: str) -> dict:
    catalog = load_unit_catalog_raw()
    units = catalog.get("units", {})

    if unit_key not in units:
        raise KeyError(f"Unknown unit_key: {unit_key}")

    return units[unit_key]