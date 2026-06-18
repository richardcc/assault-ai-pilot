from assault_model.map.hex_ownership import HexOwnership
from assault_model.state.game_state import GameState


def test_side_to_ownership_excludes_none():
    state = GameState.__new__(GameState)
    state.turn_order = ["GE", "US"]

    mapping = GameState._build_side_ownership(state)

    assert mapping["GE"] == HexOwnership.SIDE_A
    assert mapping["US"] == HexOwnership.SIDE_B
    assert HexOwnership.NONE not in mapping.values()


def test_side_to_ownership_raises_when_more_sides_than_control_slots():
    state = GameState.__new__(GameState)
    state.turn_order = ["A", "B", "C"]

    try:
        GameState._build_side_ownership(state)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for unsupported side count")
