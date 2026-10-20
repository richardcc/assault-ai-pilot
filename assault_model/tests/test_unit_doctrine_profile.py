from pathlib import Path
from assault_model.paths import UNIT_CATALOG_PATH
from assault_model.units.catalog_loader import load_unit_catalog
from assault_model.units.unit_type import DoctrineProfile


def test_doctrine_profiles_loaded_for_all_units():
    """Verify that every single unit in unit_catalog.json has a valid, non-default DoctrineProfile."""
    catalog = load_unit_catalog(UNIT_CATALOG_PATH)
    assert len(catalog) >= 19, f"Catalog has {len(catalog)} units, expected at least 19"

    valid_roles = {"SPEARHEAD", "FIRE_SUPPORT", "RECON", "SCREEN", "COMMAND"}

    for code, unit in catalog.items():
        doc = unit.doctrine_profile
        assert isinstance(doc, DoctrineProfile), f"Unit {code} does not have a DoctrineProfile instance"
        assert doc.default_role in valid_roles, f"Unit {code} has invalid default_role '{doc.default_role}'"
        assert len(doc.optimal_engagement_range) == 2, f"Unit {code} optimal range invalid"
        assert doc.optimal_engagement_range[0] <= doc.optimal_engagement_range[1], f"Unit {code} min range > max range"
        assert len(doc.preferred_terrain) > 0, f"Unit {code} preferred terrain cannot be empty"
        assert doc.cohesion_weight > 0.0, f"Unit {code} cohesion_weight must be positive"
        assert doc.fallback_threshold_hp >= 1, f"Unit {code} fallback threshold must be >= 1"


def test_doctrine_role_specialization_expectations():
    """Verify that specialized heavy weapons and assault units receive the correct doctrinal role."""
    catalog = load_unit_catalog(UNIT_CATALOG_PATH)

    # Heavy weapons must be FIRE_SUPPORT
    assert catalog["GE_HEAVY_MG_42"].doctrine_profile.default_role == "FIRE_SUPPORT"
    assert catalog["US_81MM_MORTAR"].doctrine_profile.default_role == "FIRE_SUPPORT"
    assert catalog["IT_20MM_BREDA_AA_43"].doctrine_profile.default_role == "FIRE_SUPPORT"

    # Assault units must be SPEARHEAD
    assert catalog["GE_FJ_RIFLES_43"].doctrine_profile.default_role == "SPEARHEAD"
    assert catalog["US_AIRBORNE_RIFLES_43"].doctrine_profile.default_role == "SPEARHEAD"
    assert catalog["GE_GRENADIERS_43"].doctrine_profile.default_role == "SPEARHEAD"

    # Recon units must be RECON
    assert catalog["US_RANGERS_43"].doctrine_profile.default_role == "RECON"
    assert catalog["US_SNIPER_43"].doctrine_profile.default_role == "RECON"
    assert catalog["IT_SNIPER_43"].doctrine_profile.default_role == "RECON"

    # Line squads must be SCREEN
    assert catalog["GE_RIFLES_43"].doctrine_profile.default_role == "SCREEN"
    assert catalog["IT_RIFLES_43"].doctrine_profile.default_role == "SCREEN"


def test_doctrine_profile_serialization_roundtrip():
    """Verify that DoctrineProfile from_dict accurately parses all custom fields."""
    data = {
        "default_role": "FIRE_SUPPORT",
        "optimal_engagement_range": [3, 8],
        "preferred_terrain": ["HILL", "BUILDING"],
        "cohesion_weight": 1.35,
        "fallback_threshold_hp": 2,
        "mutation_rules": {
            "allow_spearhead_if_vp_deficit": False,
            "allow_close_defense_on_flank": True,
        },
    }
    profile = DoctrineProfile.from_dict(data)
    assert profile.default_role == "FIRE_SUPPORT"
    assert profile.optimal_engagement_range == (3, 8)
    assert profile.preferred_terrain == ("HILL", "BUILDING")
    assert profile.cohesion_weight == 1.35
    assert profile.fallback_threshold_hp == 2
    assert profile.allow_spearhead_if_vp_deficit is False
    assert profile.allow_close_defense_on_flank is True
