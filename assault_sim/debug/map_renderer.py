# assault_sim/debug/map_renderer.py

class MapRenderer:
    """
    Renders the full game map with:
    - terrain (water / clear),
    - hex state (building 🏠 / woods 🌳),
    - units (🔵 GE / 🔴 US),
    - victory points 🚩.
    """

    def __init__(self):
        self.game_map = None
        self.units = []
        self.vps = set()

    def update_state(self, payload: dict):
        self.game_map = payload.get("game_map")
        self.units = payload.get("units", [])

        self.vps.clear()
        vp_tracker = payload.get("vp_tracker")

        if vp_tracker and getattr(vp_tracker, "conditions", None):
            for vp in vp_tracker.conditions.points:
                self.vps.add(vp.hex_coords)

    def render(self, turn):
        print(f"\n=== MAP STATE — TURN {turn} ===\n")

        if not self.game_map:
            print("(map unavailable)")
            return

        # -------------------------------------------------
        # UNIT LOOKUP
        # -------------------------------------------------
        unit_at = {
            (u.position.q, u.position.r): u
            for u in self.units
            if getattr(u, "alive", True) and u.position
        }

        max_q = max(h.q for h in self.game_map.hexes)
        max_r = max(h.r for h in self.game_map.hexes)

        # -------------------------------------------------
        # HEADER
        # -------------------------------------------------
        print("   q→ ", end="")
        for q in range(max_q + 1):
            print(f"{q:>3}", end=" ")
        print("\nr↓")

        # -------------------------------------------------
        # MAP LOOP
        # -------------------------------------------------
        for r in range(max_r + 1):
            indent = "  " if r % 2 else ""
            print(f"{r:<2} {indent}", end="")

            for q in range(max_q + 1):
                hex_ = self.game_map.get_hex(q, r)

                if not hex_:
                    print("     ", end="")
                    continue

                # -------------------------------------------------
                # BASE TERRAIN
                # -------------------------------------------------
                if hex_.terrain.value == "water":
                    symbol = "~~~"
                else:
                    symbol = " . "

                # -------------------------------------------------
                # HEX STATE (terrain features)
                # -------------------------------------------------
                hs = self.game_map.get_hex_state(q, r)
                if hs:
                    if getattr(hs, "building", False):
                        symbol = "🏠"
                    elif getattr(hs, "woods", False):
                        symbol = "🌳"

                # -------------------------------------------------
                # VICTORY POINT (overlay base)
                # -------------------------------------------------
                if (q, r) in self.vps:
                    symbol = "🚩"

                # -------------------------------------------------
                # UNIT OVERLAY (priority)
                # -------------------------------------------------
                if (q, r) in unit_at:
                    u = unit_at[(q, r)]
                    icon = "🔵" if u.side == "GE" else "🔴"

                    # suppression indicator
                    if getattr(u, "suppressed", False):
                        icon += "😵"

                    # keep VP visible if present
                    if (q, r) in self.vps:
                        symbol = f"{icon}🚩"
                    else:
                        symbol = f"{icon}{symbol.strip()}"

                # print
                print(f"{symbol:>4}", end=" ")

            print()

        # -------------------------------------------------
        # LEGEND
        # -------------------------------------------------
        print(
            "\nLegend: . CLEAR | ~~~ WATER | 🏠 BUILDING | 🌳 WOODS "
            "| 🔵 GE | 🔴 US | 🚩 VP\n"
        )