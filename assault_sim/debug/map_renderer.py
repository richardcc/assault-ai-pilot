class MapRenderer:
    """
    Renders the map from payload (JSON only).
    No dependency on game_map or engine objects.
    """

    def __init__(self):
        self.hexes = []
        self.units = []
        self.vps = set()

    # -------------------------------------------------
    # STATE UPDATE
    # -------------------------------------------------
    def update_state(self, payload: dict):
        self.hexes = payload.get("hexes", [])
        self.units = payload.get("units", [])

        # ✅ NUEVO FORMATO VPs
        self.vps = set(tuple(v) for v in payload.get("vps", []))

    # -------------------------------------------------
    # RENDER
    # -------------------------------------------------
    def render(self, turn):

        print(f"\n=== MAP STATE — TURN {turn} ===\n")

        if not self.hexes:
            print("(map unavailable)")
            return

        # -------------------------------------------------
        # BUILD LOOKUPS
        # -------------------------------------------------
        hex_lookup = {(h["q"], h["r"]): h for h in self.hexes}

        unit_at = {
            (u["q"], u["r"]): u
            for u in self.units
            if u.get("q") is not None and u.get("r") is not None
        }

        max_q = max(h["q"] for h in self.hexes)
        max_r = max(h["r"] for h in self.hexes)

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

                hex_ = hex_lookup.get((q, r))

                if not hex_:
                    print("     ", end="")
                    continue

                # -------------------------
                # TERRAIN
                # -------------------------
                terrain = hex_.get("terrain", "clear")

                if terrain == "water":
                    symbol = "~~~"
                elif terrain == "building_single":
                    symbol = "🏠"
                elif terrain == "building_multi":
                    symbol = "🏢"
                elif terrain == "light_forest":
                    symbol = "🌳"
                elif terrain == "olive_vine_grove":
                    symbol = "🌿"
                elif terrain == "rocky":
                    symbol = "⛰️"
                else:
                    symbol = " . "

                # -------------------------
                # VP
                # -------------------------
                if (q, r) in self.vps:
                    symbol = "🚩"

                # -------------------------
                # UNIT OVERLAY
                # -------------------------
                if (q, r) in unit_at:

                    u = unit_at[(q, r)]
                    icon = "🔵" if u["side"] == "GE" else "🔴"

                    if (q, r) in self.vps:
                        symbol = f"{icon}🚩"
                    else:
                        symbol = f"{icon}{symbol.strip()}"

                print(f"{symbol:>4}", end=" ")

            print()

        # -------------------------------------------------
        # LEGEND
        # -------------------------------------------------
        print(
            "\nLegend: . CLEAR | ~~~ WATER | 🏠 SINGLE | 🏢 MULTI | ⛰️ ROCKY\n"
            "        🌳 FOREST | 🌿 GROVE | 🔵 GE | 🔴 US | 🚩 VP\n"
        )