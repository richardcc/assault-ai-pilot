from assault_model.map.hex_coord import HexCoord
from assault_model.map.hex_utils import hex_distance, neighbors, safe_hex_distance


def test_hex_distance_is_symmetric_on_sample_points():
    samples = [
        ((0, 0), (0, 0)),
        ((0, 0), (1, 0)),
        ((3, 2), (7, 5)),
        ((10, 4), (2, 9)),
        ((-2, 3), (4, -1)),
    ]
    for a, b in samples:
        assert hex_distance(a, b) == hex_distance(b, a)


def test_neighbors_are_unique_and_distance_one():
    for origin in [(0, 0), (1, 0), (2, 3), (5, 8)]:
        ns = neighbors(origin)
        assert len(ns) == 6
        assert len(set(ns)) == 6
        for n in ns:
            assert hex_distance(origin, n) == 1
            assert origin in neighbors(n)


def test_safe_hex_distance_accepts_hexcoord_and_tuple():
    a = HexCoord(4, 3)
    b = (6, 7)
    assert safe_hex_distance(a, b) == safe_hex_distance((4, 3), HexCoord(6, 7))


def test_safe_hex_distance_returns_sentinel_on_invalid():
    assert safe_hex_distance(None, (0, 0)) == 999
    assert safe_hex_distance((0, 0), None) == 999
    assert safe_hex_distance("bad", (0, 0)) == 999
