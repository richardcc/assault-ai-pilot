from __future__ import annotations

import pytest
from fastapi.encoders import jsonable_encoder

from assault_model.map.hex_coord import HexCoord
from assault_model.core.scenario_loader import load_scenario
from assault_model.map.map_piece_loader import load_map_piece_catalog
from assault_model.units.catalog_loader import load_unit_catalog
from assault_model.paths import (
    ASSETS_DIR,
    CATALOGS_DIR,
    MAP_PIECE_CATALOG_PATH,
    SCENARIOS_DIR,
    UNIT_CATALOG_PATH,
)
from assault_backend.services.scenario_service_ui import load_ui_scenario


def test_hex_coord_protocols_and_serialization():
    coord = HexCoord(3, 7)

    # 1. Unpacking (sequence protocol)
    q, r = coord
    assert q == 3 and r == 7

    # 2. Index access
    assert coord[0] == 3
    assert coord[1] == 7
    with pytest.raises(IndexError):
        _ = coord[2]

    # 3. Key access (mapping protocol)
    assert coord["q"] == 3
    assert coord["r"] == 7
    with pytest.raises(KeyError):
        _ = coord["invalid"]

    # 4. dict conversion
    as_dict = dict(coord)
    assert as_dict == {"q": 3, "r": 7}

    # 5. Helper methods
    assert coord.to_dict() == {"q": 3, "r": 7}
    assert coord.to_tuple() == (3, 7)
    assert coord.to_list() == [3, 7]

    # 6. Equality with tuples / lists
    assert coord == (3, 7)
    assert coord == [3, 7]
    assert coord == HexCoord(3, 7)
    assert coord != (3, 8)

    # 7. FastAPI jsonable_encoder native compatibility
    encoded = jsonable_encoder(coord)
    assert encoded == {"q": 3, "r": 7}


def test_hex_coord_from_any():
    base = HexCoord(4, 9)

    # Idempotent
    assert HexCoord.from_any(base) is base

    # Sequence
    assert HexCoord.from_any([4, 9]) == base
    assert HexCoord.from_any((4, 9)) == base

    # Dict variants
    assert HexCoord.from_any({"q": 4, "r": 9}) == base
    assert HexCoord.from_any({"col": 4, "row": 9}) == base
    assert HexCoord.from_any({"position": [4, 9]}) == base
    assert HexCoord.from_any({"position": {"q": 4, "r": 9}}) == base
    assert HexCoord.from_any({"origin": [4, 9]}) == base
    assert HexCoord.from_any({"coords": (4, 9)}) == base
    assert HexCoord.from_any({"hex": [4, 9]}) == base

    # Object with attributes
    class PosHolder:
        q = 4
        r = 9

    assert HexCoord.from_any(PosHolder()) == base


def test_scenario_loading_with_unified_coordinates():
    units_catalog = load_unit_catalog(UNIT_CATALOG_PATH)
    pieces_catalog = load_map_piece_catalog(MAP_PIECE_CATALOG_PATH)

    # Test both active scenarios load cleanly with normalized coordinates
    sc_cittadina = load_scenario(SCENARIOS_DIR / "battaglia_cittadina_2_1.json", units_catalog, pieces_catalog)
    assert sc_cittadina is not None
    assert len(sc_cittadina.units) > 0

    for u in sc_cittadina.units:
        assert isinstance(u.position, HexCoord)
        assert hasattr(u.position, "q")
        assert hasattr(u.position, "r")
        assert dict(u.position) == {"q": u.position.q, "r": u.position.r}

    sc_piedi = load_scenario(SCENARIOS_DIR / "mettete_i_piedi_terra_1.json", units_catalog, pieces_catalog)
    assert sc_piedi is not None
    assert len(sc_piedi.units) > 0


def test_ui_scenario_service_canonical_coordinates():
    ui_data = load_ui_scenario("battaglia_cittadina_2_1")
    assert "units" in ui_data
    assert len(ui_data["units"]) > 0

    for u in ui_data["units"]:
        assert "q" in u
        assert "r" in u
        assert "position" in u
        assert u["position"] == {"q": u["q"], "r": u["r"]}

    assert "map" in ui_data
    for piece in ui_data["map"]["pieces"]:
        assert "origin" in piece
        assert "q" in piece
        assert "r" in piece
        assert piece["origin"] == [piece["q"], piece["r"]]
