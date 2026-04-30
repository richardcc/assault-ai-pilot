# assault_sim/debug/console_observer.py
#
# Rich console observer.
# ✅ Fancy as hell (colors, dice, emojis)
# ✅ Correct turn semantics
# ✅ MAP rendered ONLY:
#    - at RESET (start of turn 1)
#    - at TURN_END (end of real turn)
# ❌ NEVER at TURN_STATE (activation end)

class ConsoleObserver:
    def __init__(self):
        self.current_turn = None
        self._last_game_map = None
        self._last_units = []

    # -------------------------------------------------
    # Callable interface (EventBus contract)
    # -------------------------------------------------
    def __call__(self, event: dict):
        event_type = event.get("type")
        payload = event.get("payload", {})

        # -------------------------------------------------
        # RESET — MAP AT START
        # -------------------------------------------------
        if event_type == "RESET":
            print("\n=== SIMULATION RESET ===")
            print(f"Scenario: {payload.get('scenario')}")
            print(f"Starting turn: {payload.get('turn')}")
            print("========================\n")

            game_map = payload.get("game_map")
            if game_map:
                self._render_map(game_map, [], "INITIAL MAP LAYOUT")

        # -------------------------------------------------
        # UNIT LOADED
        # -------------------------------------------------
        elif event_type == "UNIT_LOADED":
            print(
                f"[UNIT] {payload.get('unit_id')} "
                f"side={payload.get('side')} "
                f"pos={payload.get('position')}"
            )

        # -------------------------------------------------
        # ACTION START
        # -------------------------------------------------
        elif event_type == "ACTION":
            self.current_turn = payload.get("turn")
            print(
                f"\n[TURN {self.current_turn}] "
                f"{self._unit_label(payload.get('active_unit'), payload.get('hp'))} "
                f"-> {payload.get('action')}"
            )

        # -------------------------------------------------
        # ACTION EFFECT (movement / HP)
        # -------------------------------------------------
        elif event_type == "ACTION_EFFECT":
            uid = payload.get("unit_id")

            if payload.get("moved"):
                print(
                    f"  🧭 MOVE {self._unit_label(uid, payload.get('hp_after'))}: "
                    f"{payload.get('from')} → {payload.get('to')} "
                    f"({payload.get('direction')})"
                )

            if payload.get("hp_before") != payload.get("hp_after"):
                print(
                    f"  ❤️ HP {uid}: "
                    f"{payload.get('hp_before')} → "
                    f"{payload.get('hp_after')} {self._hearts(payload.get('hp_after'))}"
                )

        # -------------------------------------------------
        # ACTIVATION END (INFO ONLY)
        # -------------------------------------------------
        elif event_type == "TURN_STATE":
            print(
                f"[END TURN {payload.get('turn')}] "
                f"next active={payload.get('active_unit')}"
            )
            # ❌ NO MAP HERE

        # -------------------------------------------------
        # ✅ REAL TURN END → MAP
        # -------------------------------------------------
        elif event_type == "TURN_END":
            print(f"\n=== END OF TURN {payload.get('turn')} ===")
            if self._last_game_map:
                self._render_map(
                    self._last_game_map,
                    self._last_units,
                    f"MAP STATE — TURN {payload.get('turn')}",
                )

        # -------------------------------------------------
        # MAP STATE (CACHE ONLY)
        # -------------------------------------------------
        elif event_type == "MAP_STATE":
            self._last_game_map = payload.get("game_map")
            self._last_units = payload.get("units", [])

        # -------------------------------------------------
        # ✅ FULL COMBAT NARRATION
        # -------------------------------------------------
        elif event_type == "CLOSE_COMBAT_ROUND":
            atk = payload.get("attacker_id")
            dfn = payload.get("defender_id")

            print(
                f"  ⚔️  CC ROUND {payload.get('round')} "
                f"[{atk} vs {dfn}]"
            )

            print(
                f"    ATK dice: {self._format_dice(payload.get('attacker_attack_dice'))}"
            )
            print(
                f"    ATK def : {self._format_dice(payload.get('attacker_defense_dice'))}"
            )
            print(
                f"    DEF dice: {self._format_dice(payload.get('defender_attack_dice'))}"
            )
            print(
                f"    DEF def : {self._format_dice(payload.get('defender_defense_dice'))}"
            )

            print(
                f"    ATK {self._unit_label(atk, payload.get('attacker_hp_after'))}"
            )
            print(
                f"    DEF {self._unit_label(dfn, payload.get('defender_hp_after'))}"
            )

        elif event_type == "CLOSE_COMBAT_END":
            if payload.get("outcome") == "MUTUAL_DESTRUCTION":
                print(
                    f"  💥 MUTUAL DESTRUCTION "
                    f"[{payload.get('attacker_id')} vs {payload.get('defender_id')}]"
                )
            else:
                print(
                    f"  🏁 CC END "
                    f"winner={payload.get('winner')} "
                    f"({payload.get('outcome')})"
                )

        # -------------------------------------------------
        # UNIT REMOVED
        # -------------------------------------------------
        elif event_type == "UNIT_REMOVED":
            print(
                f"  ☠️ UNIT REMOVED: {payload.get('unit_id')} "
                f"({payload.get('reason')})"
            )

        # -------------------------------------------------
        # MATCH END
        # -------------------------------------------------
        elif event_type == "MATCH_END":
            print("\n" + "=" * 40)
            print("🏆🏆🏆   MATCH FINISHED   🏆🏆🏆")
            print("=" * 40)
            print(f"🎖️  WINNER: {payload.get('winner')}")
            print(f"📜  Reason: {payload.get('reason')}")
            print("🔥  Last side standing!")
            print("=" * 40 + "\n")

    # -------------------------------------------------
    # Helpers (the fancy stuff)
    # -------------------------------------------------
    def _hearts(self, hp):
        if hp is None or hp <= 0:
            return "☠️"
        return "❤️" * hp

    def _unit_label(self, unit_id, hp):
        if not unit_id:
            return "UNKNOWN"
        if hp is None:
            return unit_id
        return f"{unit_id} (HP={hp} {self._hearts(hp)})"

    def _color_die(self, die):
        if die is None:
            return "—"
        name = str(die)
        if "CRITICAL" in name:
            return f"\033[91m{name}\033[0m"   # red
        if "DAMAGE" in name:
            return f"\033[93m{name}\033[0m"   # yellow
        if "SUPPRESS" in name:
            return f"\033[94m{name}\033[0m"   # blue
        if "BLANK" in name:
            return f"\033[90m{name}\033[0m"   # gray
        return name

    def _format_dice(self, dice):
        if not dice:
            return "—"
        return " ".join(self._color_die(d) for d in dice)

    # -------------------------------------------------
    # MAP RENDERING
    # -------------------------------------------------
    def _render_map(self, game_map, units, title: str):
        print(f"\n=== {title} ===\n")

        max_q = max(h.q for h in game_map.hexes)
        max_r = max(h.r for h in game_map.hexes)
        unit_at = {u.position: u for u in units if getattr(u, "alive", True)}

        print("   q→ ", end="")
        for q in range(max_q + 1):
            print(f"{q:>3}", end=" ")
        print("\nr↓")

        for r in range(max_r + 1):
            indent = "  " if r % 2 == 1 else ""
            print(f"{r:<2} {indent}", end="")
            for q in range(max_q + 1):
                hex_ = game_map.get_hex(q, r)
                if not hex_:
                    print("   ", end=" ")
                    continue

                state = game_map.get_hex_state(q, r)
                pos = (q, r)

                if pos in unit_at:
                    symbol = "🔵" if unit_at[pos].side == "GE" else "🔴"
                elif hex_.terrain.value == "water":
                    symbol = "~~~"
                else:
                    symbol = " . "

                if pos not in unit_at and state:
                    if getattr(state, "building", False):
                        symbol = "🏠"
                    elif getattr(state, "woods", False):
                        symbol = "🌳"

                print(f"{symbol:>3}", end=" ")
            print()

        print(
            "\nLegend: . CLEAR | ~~~ WATER | 🏠 BUILDING | 🌳 WOODS | 🔵 GE | 🔴 US\n"
        )