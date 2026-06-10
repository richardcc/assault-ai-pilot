from assault_model.map.hex import Hex
from assault_model.map.hex_utils import neighbors
from assault_model.map.map import Map
from assault_model.map.terrain import Terrain


def _irregular_map() -> Map:
    # Deliberately sparse/non-rectangular footprint.
    hexes = [
        Hex(0, 0, Terrain.CLEAR),
        Hex(1, 0, Terrain.CLEAR),
        Hex(0, 1, Terrain.CLEAR),
        Hex(2, 1, Terrain.CLEAR),
        Hex(2, 2, Terrain.CLEAR),
    ]
    return Map(hexes=hexes)


def _existing_neighbor_coords(game_map: Map, q: int, r: int):
    return {
        (nq, nr)
        for (nq, nr) in neighbors((q, r))
        if game_map.get_hex(nq, nr) is not None
    }


def test_neighbors_filtered_by_map_border_corner_hex():
    game_map = _irregular_map()
    # (0,0) is a border corner in this irregular footprint.
    assert _existing_neighbor_coords(game_map, 0, 0) == {(1, 0), (0, 1)}


def test_neighbors_filtered_by_map_border_inner_hex():
    game_map = _irregular_map()
    # In odd-r coordinates, (1,0) is adjacent to both (0,0) and (0,1)
    # when those hexes exist in the sparse map footprint.
    assert _existing_neighbor_coords(game_map, 1, 0) == {(0, 0), (0, 1)}


def test_neighbor_relation_is_symmetric_over_existing_map_edges():
    game_map = _irregular_map()
    for h in game_map.all_hexes():
        here = (h.q, h.r)
        for nb in _existing_neighbor_coords(game_map, h.q, h.r):
            assert here in _existing_neighbor_coords(game_map, nb[0], nb[1])
