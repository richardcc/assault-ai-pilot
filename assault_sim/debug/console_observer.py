# assault_sim/debug/console_observer.py

import pprint
from assault_model.combat.dice_face import DiceFace


class ConsoleObserver:
    def __init__(self, debug_raw: bool = False):
        self.debug_raw = debug_raw

        self._last_game_map = None
        self._last_units = []
        self._vp_flags = set()   # posiciones con VP (q, r)

        self._current_turn = None
        self._turn_buffer = []

        self._pp = pprint.PrettyPrinter(indent=2, width=120, compact=False)

    # =================================================
    # EVENT BUS ENTRY POINT
    # =================================================
    def __call__(self, event: dict):

        if self.debug_raw:
            print("\n" + "-" * 80)
            print("📡 EVENT RECEIVED (RAW)")
            print("-" * 80)
            self._pp.pprint(event)
            print("-" * 80)

        event_type = event.get("type")
        payload = event.get("payload", {})

        # ---------------- RESET ----------------
        if event_type == "RESET":
            print("\n=== SIMULATION RESET ===")
            print(f"Scenario: {payload.get('scenario')}")
            print(f"Starting turn: {payload.get('turn')}")
            print("========================\n")

        # ---------------- UNIT LOADED ----------------
        elif event_type == "UNIT_LOADED":
            uid = payload.get("unit_id")
            print(
                f"[UNIT] {self._unit_label(uid)} "
                f"side={payload.get('side')} "
                f"pos={payload.get('position')}"
            )

        # ---------------- MAP STATE ----------------
        elif event_type == "MAP_STATE":
            self._last_game_map = payload.get("game_map")
            self._last_units = payload.get("units", [])

            # VP -> banderas
            self._vp_flags.clear()
            vp_tracker = payload.get("vp_tracker")
            if vp_tracker and getattr(vp_tracker, "conditions", None):
                for vp in vp_tracker.conditions.points:
                    self._vp_flags.add(vp.hex_coords)

        # ---------------- ACTION ----------------
        elif event_type == "ACTION":
            turn = payload.get("turn")
            uid = payload.get("active_unit")

            if self._current_turn != turn:
                self._flush_turn()
                self._current_turn = turn
                print(f"[TURN {turn}]")

            self._turn_buffer.append(
                f"         {self._unit_label(uid)} -> {payload.get('action')}"
            )

        # ---------------- ACTION EFFECT: MOVEMENT ----------------
        elif (
            event_type == "ACTION_EFFECT"
            and payload.get("moved")
        ):
            uid = payload.get("unit_id")
            arrow = self._movement_arrow(
                payload.get("from"), payload.get("to")
            )
            if self._turn_buffer:
                self._turn_buffer[-1] += (
                    f" 🧭 MOVE {self._unit_label(uid)} {arrow} "
                    f"({payload.get('from')} → {payload.get('to')})"
                )

        # ---------------- ACTION EFFECT: CLOSE COMBAT ----------------
        elif (
            event_type == "ACTION_EFFECT"
            and payload.get("action") == "CloseCombat"
        ):
            attacker = payload["attacker"]
            defender = payload["defender"]

            self._turn_buffer.append("         💥 COMBAT RESULT")

            def render_dice(dice_names, unit_id):
                return " ".join(
                    self._render_die(DiceFace[name], unit_id)
                    for name in dice_names
                )

            # Dice pools
            self._turn_buffer.append(
                f"             🎲 {self._unit_label(attacker)} "
                f"ATK [{render_dice(payload['attacker_attack_dice'], attacker)}] "
                f"DEF [{render_dice(payload['attacker_defense_dice'], attacker)}]"
            )

            self._turn_buffer.append(
                f"             🎲 {self._unit_label(defender)} "
                f"ATK [{render_dice(payload['defender_attack_dice'], defender)}] "
                f"DEF [{render_dice(payload['defender_defense_dice'], defender)}]"
            )

            # Damage
            att_loss = payload["attacker_hp_before"] - payload["attacker_hp_after"]
            def_loss = payload["defender_hp_before"] - payload["defender_hp_after"]

            if def_loss > 0:
                self._turn_buffer.append(
                    f"                 → {self._unit_label(defender)} -{def_loss}❤️"
                )

            if att_loss > 0:
                self._turn_buffer.append(
                    f"                 → {self._unit_label(attacker)} -{att_loss}❤️"
                )

            # Outcome
            self._turn_buffer.append(
                f"             🏁 Outcome: {payload['outcome']}"
            )

            if payload.get("winner"):
                self._turn_buffer.append(
                    f"             🏆 Winner: {self._unit_label(payload['winner'])}"
                )

        # ---------------- TURN END ----------------
        elif event_type == "TURN_END":
            self._flush_turn()
            self._render_map(f"MAP STATE — TURN {payload.get('turn')}")
            print()

    # =================================================
    # TURN BUFFER
    # =================================================
    def _flush_turn(self):
        for line in self._turn_buffer:
            print(line)
        self._turn_buffer.clear()
        self._current_turn = None

    # =================================================
    # MAP RENDERING (TERRAIN + VP FLAGS)
    # =================================================
    def _render_map(self, title: str):
        print(f"\n=== {title} ===\n")

        game_map = self._last_game_map
        units = self._last_units

        if not game_map:
            print("(map unavailable)")
            return

        max_q = max(h.q for h in game_map.hexes)
        max_r = max(h.r for h in game_map.hexes)

        unit_at = {u.position: u for u in units if getattr(u, "alive", True)}

        print("   q→ ", end="")
        for q in range(max_q + 1):
            print(f"{q:>3}", end=" ")
        print("\nr↓")

        for r in range(max_r + 1):
            indent = "  " if r % 2 else ""
            print(f"{r:<2} {indent}", end="")

            for q in range(max_q + 1):
                hex_ = game_map.get_hex(q, r)
                if not hex_:
                    print("     ", end="")
                    continue

                pos = (q, r)

                # Terrain
                if hex_.terrain.value == "water":
                    symbol = "~~~"
                else:
                    symbol = " . "

                # Features
                map_state = game_map.get_hex_state(q, r)
                if map_state:
                    if getattr(map_state, "building", False):
                        symbol = "🏠"
                    elif getattr(map_state, "woods", False):
                        symbol = "🌳"

                # Unit
                if pos in unit_at:
                    u = unit_at[pos]
                    icon = "🔵" if u.side == "GE" else "🔴"
                    symbol = f"{icon}{symbol.strip()}"

                # VP flag
                if pos in self._vp_flags:
                    if symbol.strip().startswith(("🔵", "🔴")):
                        symbol = f"{symbol.strip()}🚩"
                    else:
                        symbol = " 🚩"

                print(f"{symbol:>4}", end=" ")
            print()

        print(
            "\nLegend: . CLEAR | ~~~ WATER | 🏠 BUILDING | 🌳 WOODS "
            "| 🔵 GE | 🔴 US | 🚩 VP\n"
        )

    # =================================================
    # HELPERS
    # =================================================
    def _unit_label(self, unit_id: str) -> str:
        for u in self._last_units:
            if u.unit_id == unit_id:
                icon = "🔵" if u.side == "GE" else "🔴"
                hearts = "❤️" * max(0, getattr(u, "hp", 0))
                return f"{icon}{unit_id} {hearts}".strip()
        return unit_id

    def _render_die(self, face: DiceFace, unit_id: str) -> str:
        color = "🔵" if unit_id.startswith("GE") else "🔴"
        icon = {
            DiceFace.CRITICAL: "💥",
            DiceFace.DAMAGE: "❤️",
            DiceFace.SUPPRESS: "😵",
            DiceFace.BLANK: "⚪",
        }.get(face, "?")
        return f"{color}{icon}"

    def _movement_arrow(self, frm, to) -> str:
        dq = to[0] - frm[0]
        dr = to[1] - frm[1]

        if dq == 1 and dr == 0:
            return "➡️"
        if dq == -1 and dr == 0:
            return "⬅️"
        if dq == 0 and dr == 1:
            return "⬇️"
        if dq == 0 and dr == -1:
            return "⬆️"
        return "•"