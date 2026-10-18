from assault_model.map.hex import Hex
from assault_model.map.map import Map
from assault_model.map.terrain import Terrain
from assault_model.map.hex_ownership import HexOwnership
from assault_model.map.hex_coord import HexCoord
from assault_model.map.hex_utils import hex_range, hex_distance
from types import SimpleNamespace
from assault_model.core.victory_conditions import VictoryConditions
from assault_model.state.game_state import GameState


def _make_unit(unit_id: str, side: str, q: int, r: int):
    return SimpleNamespace(
        unit_id=unit_id,
        side=side,
        alive=True,
        suppressed=False,
        fallback=False,
        position=HexCoord(q, r),
    )


def test_hex_range_radius_3_closed_form():
    """Verify hex_range generates exactly 37 hexes for R=3 and all are within distance <= 3."""
    center = (5, 5)
    hexes = hex_range(center, radius=3)
    assert len(hexes) == 37
    assert len(set(hexes)) == 37
    for h in hexes:
        assert hex_distance(center, h) <= 3


def test_incremental_hex_control_only_touches_local_radius():
    """
    On a 16x16 map (256 hexes), moving a unit from (2, 2) to (3, 2)
    must only touch hexes within R <= 3 of those positions, leaving distant
    hexes untouched.
    """
    all_hexes = [Hex(q, r, Terrain.CLEAR) for q in range(16) for r in range(16)]
    game_map = Map(all_hexes)
    unit_us = _make_unit("US_1", "US", 2, 2)
    unit_ge = _make_unit("GE_1", "GE", 14, 14)

    state = GameState(game_map=game_map, units=[unit_us, unit_ge], turn=1, victory=None)
    assert state.hex_states[(2, 2)].ownership == state.side_to_ownership["US"]
    assert state.hex_states[(14, 14)].ownership == state.side_to_ownership["GE"]

    # When no unit moves, recalculate_hex_control returns empty set (O(1))
    touched = state.recalculate_hex_control()
    assert len(touched) == 0

    # Move US unit to (3, 2)
    unit_us.position = HexCoord(3, 2)
    touched = state.recalculate_hex_control(influence_radius=3)

    # Touched hexes must be <= 74 (bounded by R=3 around (2, 2) and (3, 2))
    assert len(touched) > 0
    assert len(touched) <= 74
    # Distant hex (14, 14) must NOT have been touched in the active set
    assert (14, 14) not in touched
    assert state.hex_states[(14, 14)].ownership == state.side_to_ownership["GE"]

    # (2, 2) is now empty, (3, 2) is now US controlled
    assert state.hex_states[(2, 2)].ownership == HexOwnership.NONE
    assert state.hex_states[(3, 2)].ownership == state.side_to_ownership["US"]


def test_incremental_vp_persistence_and_capture():
    """VP hexes persist until occupied by another side."""
    all_hexes = [Hex(q, r, Terrain.CLEAR) for q in range(10) for r in range(10)]
    game_map = Map(all_hexes)
    unit_us = _make_unit("US_1", "US", 0, 0)
    victory = VictoryConditions.from_json({"value_per_hex": 2, "hexes": [[0, 0], [9, 9]]})

    state = GameState(game_map=game_map, units=[unit_us], turn=1, victory=victory)
    state.recalculate_hex_control(force_full=True)

    # US starts on (0, 0) -> controls it
    assert state.hex_states[(0, 0)].ownership == state.side_to_ownership["US"]
    assert state.hex_states[(9, 9)].ownership == HexOwnership.NONE

    # US unit moves away from (0, 0) to (1, 0)
    unit_us.position = HexCoord(1, 0)
    state.recalculate_hex_control(influence_radius=3)

    # VP at (0, 0) MUST persist even though unit left it
    assert state.hex_states[(0, 0)].ownership == state.side_to_ownership["US"]
    assert state.hex_states[(1, 0)].ownership == state.side_to_ownership["US"]


def test_stacking_incremental_control():
    """
    Two units of the same side stack on the same hex.
    When one moves away, the hex must remain controlled by the remaining unit.
    """
    game_map = Map([Hex(0, 0, Terrain.CLEAR), Hex(1, 0, Terrain.CLEAR)])
    u1 = _make_unit("US_1", "US", 0, 0)
    u2 = _make_unit("US_2", "US", 0, 0)
    state = GameState(game_map=game_map, units=[u1, u2], turn=1, victory=None)

    assert state.hex_states[(0, 0)].ownership == state.side_to_ownership["US"]

    # u1 moves to (1, 0), u2 remains at (0, 0)
    u1.position = HexCoord(1, 0)
    state.recalculate_hex_control()

    # Both (0, 0) and (1, 0) are US controlled
    assert state.hex_states[(0, 0)].ownership == state.side_to_ownership["US"]
    assert state.hex_states[(1, 0)].ownership == state.side_to_ownership["US"]


def test_unit_elimination_incremental_control():
    """When a unit is eliminated, its occupied hex is reverted and surrounding area recalculated."""
    game_map = Map([Hex(0, 0, Terrain.CLEAR), Hex(1, 0, Terrain.CLEAR)])
    u1 = _make_unit("US_1", "US", 0, 0)
    state = GameState(game_map=game_map, units=[u1], turn=1, victory=None)

    assert state.hex_states[(0, 0)].ownership == state.side_to_ownership["US"]

    # Eliminate u1
    u1.alive = False
    touched = state.recalculate_hex_control()

    assert (0, 0) in touched
    assert state.hex_states[(0, 0)].ownership == HexOwnership.NONE
