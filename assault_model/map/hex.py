from assault_model.map.terrain import Terrain
from assault_model.map.hex_direction import HexDirection
from assault_model.map.hex_utils import neighbors as _odd_r_neighbors


class Hex:
    """
    Atomic spatial element using odd-r offset hex coordinates (q, r).

    Supports movement in 6 directions.
    """

    def __init__(self, q: int, r: int, terrain: Terrain) -> None:
        self.q = q
        self.r = r
        self.terrain = terrain

    def neighbor(self, direction: HexDirection) -> "Hex":
        return Hex(
            self.q + direction.dq,
            self.r + direction.dr,
            self.terrain,
        )

    def neighbors(self) -> list["Hex"]:
        # Vecinos odd-r consistentes con hex_distance (fuente unica en hex_utils).
        # NOTA: el terreno se copia como placeholder; los consumidores deben
        # releer el hex real via game_map.get_hex(q, r).
        return [
            Hex(nq, nr, self.terrain)
            for nq, nr in _odd_r_neighbors((self.q, self.r))
        ]

    # -------------------------------------------------
    # ✅ SIMPLIFIED TERRAIN (FINAL FORM)
    # -------------------------------------------------
    def get_terrain(self) -> str:
        """
        Returns the terrain type of the hex.
        """
        return self.terrain.value
