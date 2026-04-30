class AsciiRenderer:
    """
    Simple ASCII renderer for the assault environment.
    """

    def render(self, state, player_id=None, enemy_id=None, turn=None):
        hexes = state.hexes
        units = state.units

        # Determine bounds
        qs = [q for (q, r) in hexes.keys()]
        rs = [r for (q, r) in hexes.keys()]
        min_q, max_q = min(qs), max(qs)
        min_r, max_r = min(rs), max(rs)

        if turn is not None:
            print(f"\nTurn {turn}")

        # Render grid (simple rectangular projection)
        for r in range(min_r, max_r + 1):
            row = []
            for q in range(min_q, max_q + 1):
                hex_ = hexes.get((q, r))
                if hex_ is None:
                    cell = "   "
                elif hex_.occupant is None:
                    cell = " . "
                else:
                    unit_id = hex_.occupant
                    cell = f" {unit_id} "
                row.append(cell)
            print("".join(row))

        # Render unit info
        for unit_id, unit in units.items():
            marker = ""
            if unit_id == player_id:
                marker = "(PLAYER)"
            elif unit_id == enemy_id:
                marker = "(ENEMY)"

            print(f"{unit_id} {marker}: strength={unit.strength}")
