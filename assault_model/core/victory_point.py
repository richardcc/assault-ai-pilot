# assault_model/core/victory_point.py
class VictoryPoint:
    def __init__(
        self,
        per_turn: int,
        hex_coords: tuple[int, int],
        initial_owner: str | None = None,
    ):
        self.per_turn = per_turn
        self.hex_coords = hex_coords
        self.initial_owner = initial_owner