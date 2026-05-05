# assault_sim/debug/deployment_renderer.py

class DeploymentRenderer:
    """
    DeploymentRenderer

    Responsibility:
    - Collect UNIT_LOADED events during scenario initialization.
    - Render the initial deployment ONCE before the first turn.
    - Display unit color, life (HP), and starting position.

    Design rules:
    - Uses only payload data from UNIT_LOADED.
    - Does NOT depend on GameState.
    - Does NOT render map or turns.
    """

    def __init__(self):
        self.units = []
        self.printed = False

    # -------------------------------------------------
    # RESET
    # -------------------------------------------------
    def reset(self, payload: dict):
        """
        Reset deployment state and print scenario header.
        """
        print("\n=== SIMULATION RESET ===")
        scenario = payload.get("scenario")
        turn = payload.get("turn")

        if scenario:
            print(f"Scenario: {scenario}")
        if turn is not None:
            print(f"Starting turn: {turn}")

        print("========================\n")

        self.units.clear()
        self.printed = False

    # -------------------------------------------------
    # UNIT LOADED
    # -------------------------------------------------
    def on_unit_loaded(self, p: dict):
        """
        Store a loaded unit from UNIT_LOADED event.

        Expected payload:
        {
            "unit_id": str,
            "side": str,         # "GE" or "US"
            "position": HexCoord,
            "hp": int
        }
        """
        self.units.append(p)

    # -------------------------------------------------
    # PRINT DEPLOYMENT (ONCE)
    # -------------------------------------------------
    def maybe_print(self):
        """
        Print initial deployment once, just before TURN 1.
        """
        if self.printed or not self.units:
            return

        print("=== INITIAL DEPLOYMENT ===")
        for u in self.units:
            uid = u.get("unit_id")
            side = u.get("side")
            pos = u.get("position")
            hp = u.get("hp", 0)

            icon = "🔵" if side == "GE" else "🔴"
            hearts = "❤️" * max(0, hp)
            pos_text = f"({pos.q},{pos.r})" if pos else "?"

            print(f"{icon}{uid} {hearts} at {pos_text}")

        print("==========================\n")
        self.printed = True