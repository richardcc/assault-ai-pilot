from dataclasses import dataclass
from enum import Enum, auto


class TerrainType(Enum):
    """
    Enumeration of basic terrain categories.

    This list will grow as the engine evolves.
    """
    CLEAR = auto()
    FOREST = auto()
    URBAN = auto()
    HILL = auto()
    WATER = auto()


@dataclass(frozen=True)
class Terrain:
    """
    Describes static properties of a terrain type.

    Terrain objects are immutable data containers and
    do not implement game rules.

    Attributes:
        terrain_type: Categorical terrain identifier.
        movement_cost: Base movement cost to enter the hex.
        defense_bonus: Abstract defensive modifier.
        blocks_los: Whether this terrain blocks line of sight.
    """
    terrain_type: TerrainType
    movement_cost: int
    defense_bonus: int
    blocks_los: bool = False


# Minimal terrain library (data only)
CLEAR = Terrain(TerrainType.CLEAR, movement_cost=1, defense_bonus=0)
FOREST = Terrain(TerrainType.FOREST, movement_cost=2, defense_bonus=1)
URBAN = Terrain(TerrainType.URBAN, movement_cost=2, defense_bonus=2)
HILL = Terrain(TerrainType.HILL, movement_cost=2, defense_bonus=1)
WATER = Terrain(TerrainType.WATER, movement_cost=99, defense_bonus=0)