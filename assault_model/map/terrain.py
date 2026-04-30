from enum import Enum

class Terrain(Enum):
    """
    Base terrain type of a hex.

    Terrain represents the immutable ground substrate of a hex.
    It only includes terrain types with intrinsic, always-on rules.

    Terrain does NOT include cover, obstacles, buildings, vegetation,
    or any other elements whose effects depend on context or direction.
    """

    CLEAR = "clear"
    """
    Open ground with no inherent movement, LOS, or combat modifiers.
    Most hexes use CLEAR as their base terrain.
    """

    HILL = "hill"
    """
    Elevated ground.

    Elevation affects line of sight and positional rules.
    All elevation effects are resolved contextually by game resolvers.
    """

    WATER = "water"
    """
    Deep water terrain.

    Water is inherently impassable to most ground units.
    Movement restrictions apply regardless of unit context.
    """