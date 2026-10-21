"""
assault_model/tests/test_formation_catalog.py

Validates the canonical formation catalog schema, integrity, and domain model.
Verifies all 12 canonical formations conform strictly to wargame rules and unit catalog.
"""

from __future__ import annotations

import pytest

from assault_model.paths import FORMATION_CATALOG_PATH, UNIT_CATALOG_PATH
from assault_model.units.catalog_loader import load_unit_catalog
from assault_model.units.formation import (
    Formation,
    FormationValidationError,
    load_formation_catalog,
    save_formation_catalog,
    validate_formation_integrity,
)


def test_load_formation_catalog_success():
    """Verify formation catalog loads successfully and contains expected formations."""
    catalog = load_formation_catalog(FORMATION_CATALOG_PATH)
    assert len(catalog) >= 12

    assert "US_INF_RIFLE" in catalog
    assert "GE_FJ_RIFLE_III" in catalog
    assert "US_RANGER_ASSAULT_COMPANY" in catalog
    assert "IT_BERSAGLIERI_COMPANY" in catalog
    assert "UK_COMMANDO_TROOP" in catalog


def test_formation_data_integrity_and_unit_catalog_parity():
    """Verify that every single unit referenced in all formations exists in unit_catalog.json."""
    unit_catalog = load_unit_catalog(UNIT_CATALOG_PATH)
    formation_catalog = load_formation_catalog(FORMATION_CATALOG_PATH)

    valid_unit_ids = set(unit_catalog.keys())

    for fid, formation in formation_catalog.items():
        assert formation.id == fid
        assert formation.side in {"US", "GE", "UK", "IT"}
        assert 1 <= formation.command_rating <= 12
        assert 1 <= formation.command_points <= 4
        assert formation.experience_level in {"RECRUIT", "REGULAR", "HARDENED", "VETERAN", "ELITE"}
        assert formation.experience_units_count >= 0
        assert formation.total_unit_count > 0

        # Validate formation integrity
        validate_formation_integrity(formation, valid_unit_ids=valid_unit_ids)

        # Validate categorical partition consistency
        all_categorized = (
            list(formation.line_units)
            + list(formation.heavy_weapons)
            + list(formation.specialists)
        )
        assert len(all_categorized) == len(formation.units)


def test_formation_validation_error_on_invalid_data():
    """Ensure invalid formation specifications raise FormationValidationError."""
    bad_formation = Formation(
        id="BAD_TEST",
        name="Bad Formation",
        side="INVALID_NATION",
        units=["US_RIFLES_43"],
    )
    with pytest.raises(FormationValidationError):
        validate_formation_integrity(bad_formation)

    empty_formation = Formation(
        id="EMPTY_TEST",
        name="Empty Formation",
        side="US",
        units=[],
    )
    with pytest.raises(FormationValidationError):
        validate_formation_integrity(empty_formation)

    unknown_unit_formation = Formation(
        id="UNKNOWN_TEST",
        name="Unknown Unit Formation",
        side="US",
        units=["DOES_NOT_EXIST_XYZ"],
    )
    with pytest.raises(FormationValidationError):
        validate_formation_integrity(
            unknown_unit_formation,
            valid_unit_ids={"US_RIFLES_43"},
        )
