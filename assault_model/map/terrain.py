from enum import Enum

class Terrain(Enum):

    CLEAR = "clear"
    WATER = "water"
    HILL = "hill"

    # ✅ vegetation
    LIGHT_FOREST = "light_forest"
    HEAVY_FOREST = "heavy_forest"
    BRUSH = "brush"

    # ✅ buildings
    BUILDING_SINGLE = "building_single"
    BUILDING_MULTI = "building_multi"

    
    ROCKY = "rocky"
    OLIVE_GROVE = "olive_vine_grove"
