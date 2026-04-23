import random
import json
import os

from assault.core.game_state import GameState
from assault.core.hex import Hex
from assault.core.terrain import CLEAR, FOREST, URBAN
from assault.core.unit import Unit, UnitType, Experience


# ------------------------------------------------------------
# Level 1 – Simple duel (fixed positions, very small map)
# ------------------------------------------------------------
def simple_duel_scenario():
    state = GameState()

    for q in range(3):
        state.add_hex(Hex(q, 0, CLEAR))

    attacker = Unit(
        "A",
        UnitType.INFANTRY,
        Experience.REGULAR,
        5, 5,
        (2, 0, 0, 0),
        1,
        (0, 0),
    )

    defender = Unit(
        "D",
        UnitType.INFANTRY,
        Experience.REGULAR,
        5, 5,
        (0, 0, 0, 0),
        1,
        (2, 0),
    )

    state.add_unit(attacker)
    state.add_unit(defender)

    return state, attacker.unit_id, defender.unit_id


# ------------------------------------------------------------
# Level 2 – Same duel, longer map, fixed positions
# ------------------------------------------------------------
def simple_duel_level2():
    state = GameState()

    for q in range(5):
        state.add_hex(Hex(q, 0, CLEAR))

    attacker = Unit(
        "A",
        UnitType.INFANTRY,
        Experience.REGULAR,
        5, 5,
        (2, 0, 0, 0),
        1,
        (0, 0),
    )

    defender = Unit(
        "D",
        UnitType.INFANTRY,
        Experience.REGULAR,
        5, 5,
        (0, 0, 0, 0),
        1,
        (4, 0),
    )

    state.add_unit(attacker)
    state.add_unit(defender)

    return state, attacker.unit_id, defender.unit_id


# ------------------------------------------------------------
# Level 3b – Randomized positions
# ------------------------------------------------------------
def simple_duel_level3b():
    state = GameState()

    for q in range(5):
        state.add_hex(Hex(q, 0, CLEAR))

    attacker_x = random.choice([0, 1])
    defender_x = random.choice([3, 4])

    attacker = Unit(
        "A",
        UnitType.INFANTRY,
        Experience.REGULAR,
        5, 5,
        (2, 0, 0, 0),
        1,
        (attacker_x, 0),
    )

    defender = Unit(
        "D",
        UnitType.INFANTRY,
        Experience.REGULAR,
        5, 5,
        (0, 0, 0, 0),
        1,
        (defender_x, 0),
    )

    state.add_unit(attacker)
    state.add_unit(defender)

    return state, attacker.unit_id, defender.unit_id


# ------------------------------------------------------------
# Level 4 – Larger map
# ------------------------------------------------------------
def simple_duel_level4():
    state = GameState()

    for q in range(7):
        state.add_hex(Hex(q, 0, CLEAR))

    attacker_x = random.choice([0, 1])
    defender_x = random.choice([5, 6])

    attacker = Unit(
        "A",
        UnitType.INFANTRY,
        Experience.REGULAR,
        5, 5,
        (2, 0, 0, 0),
        1,
        (attacker_x, 0),
    )

    defender = Unit(
        "D",
        UnitType.INFANTRY,
        Experience.REGULAR,
        5, 5,
        (0, 0, 0, 0),
        1,
        (defender_x, 0),
    )

    state.add_unit(attacker)
    state.add_unit(defender)

    return state, attacker.unit_id, defender.unit_id


# ------------------------------------------------------------
# Level 5 – Terrain and cover
# ------------------------------------------------------------
def simple_duel_level5():
    state = GameState()

    terrain = [
        CLEAR,
        CLEAR,
        FOREST,
        CLEAR,
        URBAN,
        CLEAR,
        CLEAR,
    ]

    for q, t in enumerate(terrain):
        state.add_hex(Hex(q, 0, t))

    attacker_x = random.choice([0, 1])
    defender_x = random.choice([5, 6])

    attacker = Unit(
        "A",
        UnitType.INFANTRY,
        Experience.REGULAR,
        5, 5,
        (2, 0, 0, 0),
        1,
        (attacker_x, 0),
    )

    defender = Unit(
        "D",
        UnitType.INFANTRY,
        Experience.REGULAR,
        5, 5,
        (0, 0, 0, 0),
        1,
        (defender_x, 0),
    )

    state.add_unit(attacker)
    state.add_unit(defender)

    return state, attacker.unit_id, defender.unit_id


# ------------------------------------------------------------
# Level 6 – 2D map
# ------------------------------------------------------------
def simple_duel_level6():
    state = GameState()

    layout = {
        (0, 4): CLEAR,  (1, 4): FOREST, (2, 4): CLEAR,  (3, 4): URBAN,  (4, 4): CLEAR,
        (0, 3): CLEAR,  (1, 3): CLEAR,  (2, 3): CLEAR,  (3, 3): CLEAR,  (4, 3): CLEAR,
        (0, 2): CLEAR,  (1, 2): CLEAR,  (2, 2): CLEAR,  (3, 2): CLEAR,  (4, 2): CLEAR,
        (0, 1): CLEAR,  (1, 1): CLEAR,  (2, 1): CLEAR,  (3, 1): CLEAR,  (4, 1): CLEAR,
        (0, 0): CLEAR,  (1, 0): FOREST, (2, 0): CLEAR,  (3, 0): URBAN,  (4, 0): CLEAR,
    }

    for (q, r), terrain in layout.items():
        state.add_hex(Hex(q, r, terrain))

    attacker = Unit(
        "A",
        UnitType.INFANTRY,
        Experience.REGULAR,
        5, 5,
        (2, 0, 0, 0),
        1,
        (0, 2),
    )

    defender = Unit(
        "D",
        UnitType.INFANTRY,
        Experience.REGULAR,
        5, 5,
        (0, 0, 0, 0),
        1,
        (4, 2),
    )

    state.add_unit(attacker)
    state.add_unit(defender)

    return state, attacker.unit_id, defender.unit_id


# ------------------------------------------------------------
# Level 7 – Real geometry from JSON (P1)
# ------------------------------------------------------------
def simple_duel_level7_P1_from_json():
    """
    Level 7 scenario:
    Real tactical geometry loaded from map_P1.json
    """

    state = GameState()

    json_path = os.path.join("maps", "map_P1.json")
    with open(json_path, "r") as f:
        data = json.load(f)

    terrain_grid = data["hexes"]["primary_terrain"]
    bridge_grid = data["hexes"]["secondary_features"]["Bridge"]

    rows = len(terrain_grid)
    cols = len(terrain_grid[0])

    terrain_map = {
        "Open": CLEAR,
        "Brush": FOREST,
        "Olive & Vine Grove": FOREST,
        "Rocky": URBAN,
    }

    for y in range(rows):
        for x in range(cols):
            terrain_name = terrain_grid[y][x]
            is_bridge = bridge_grid[y][x]

            if terrain_name == "River" and not is_bridge:
                continue

            if is_bridge:
                terrain = CLEAR
            else:
                terrain = terrain_map.get(terrain_name, CLEAR)

            state.add_hex(Hex(x, y, terrain))

    attacker_pos = (0, rows // 2)
    defender_pos = (cols - 1, rows // 2)

    attacker = Unit(
        "A",
        UnitType.INFANTRY,
        Experience.REGULAR,
        5, 5,
        (2, 0, 0, 0),
        1,
        attacker_pos,
    )

    defender = Unit(
        "D",
        UnitType.INFANTRY,
        Experience.REGULAR,
        5, 5,
        (0, 0, 0, 0),
        1,
        defender_pos,
    )

    state.add_unit(attacker)
    state.add_unit(defender)

    return state, attacker.unit_id, defender.unit_id