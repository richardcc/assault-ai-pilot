# assault_sim/debug/console_observer.py
#
# Rich console observer.
# Shows:
# - unit name WITH HP always visible
# - movement with arrows and direction
# - HP before / after
# - close combat rounds
# - dice evidence always
# - attacker / defender ALWAYS identified
# - UNIT_REMOVED
# - MUTUAL_DESTRUCTION clearly shown
# - ✅ MATCH_END with WINNER BANNER 🎉
# - ✅ MAP RENDER (hex grid, with units, every iteration)

class ConsoleObserver:
    def __init__(self):
        self.current_turn = None

    # -------------------------------------------------
    # Helpers
    # -------------------------------------------------
    def _hearts(self, hp: int | None) -> str:
        if hp is None or hp <= 0:
            return "☠️"
        return "❤️" * hp

    def _unit_label(self, unit_id: str | None, hp: int | None) -> str:
        if not unit_id:
            return "UNKNOWN"
        if hp is None:
            return unit_id
        return f"{unit_id} (HP={hp} {self._hearts(hp)})"

    # -------------------------------------------------
    # Dice coloring helpers (ANSI)
    # -------------------------------------------------
    def _color_die(self, die):
        if die is None:
            return "—"

        name = str(die)

        if "CRITICAL" in name:
            return f"\033[91m{name}\033[0m"
        if "DAMAGE" in name:
            return f"\033[93m{name}\033[0m"
        if "SUPPRESS" in name:
            return f"\033[94m{name}\033[0m"
        if "BLANK" in name:
            return f"\033[90m{name}\033[0m"

        return name

    def _format_dice(self, dice):
        if not dice:
            return "—"
        return " ".join(self._color_die(d) for d in dice)

    # -------------------------------------------------
    # ✅ Map rendering with units (SAFE, READ-ONLY)
    # -------------------------------------------------
    def _render_map(self, game_map, units, title: str):
        print(f"\n=== {title} ===\n")

        max_q = max(h.q for h in game_map.hexes)
        max_r = max(h.r for h in game_map.hexes)

        # Build lookup of alive units by position
        unit_at = {}
        for u in units:
            if getattr(u, "alive", True):
                unit_at[u.position] = u

        # Header
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

                # ---- Visual priority ----
                # 1. Units
                if pos in unit_at:
                    symbol = "🔵" if unit_at[pos].side == "GE" else "🔴"

                # 2. Base terrain
                elif hex_.terrain.value == "water":
                    symbol = "~~~"
                else:
                    symbol = " . "

                # 3. Overlay (if no unit)
                if pos not in unit_at and state:
                    if getattr(state, "building", False):
                        symbol = "🏠"
                    elif getattr(state, "woods", False):
                        symbol = "🌳"

                print(f"{symbol:>3}", end=" ")

            print()

        print(
            "\nLegend: "
            ". CLEAR | ~~~ WATER | 🏠 BUILDING | 🌳 WOODS | 🔵 GE | 🔴 US\n"
        )

    # -------------------------------------------------
    # Event handler
    # -------------------------------------------------
    def __call__(self, event: dict):
        event_type = event.get("type")
        payload = event.get("payload", {})

        # -------------------------------------------------
        # Lifecycle
        # -------------------------------------------------
        if event_type == "RESET":
            print("\n=== SIMULATION RESET ===")
            print(f"Scenario: {payload.get('scenario')}")
            print(f"Starting turn: {payload.get('turn')}")
            print("========================\n")

            game_map = payload.get("game_map")
            if game_map:
                self._render_map(
                    game_map,
                    [],
                    title="INITIAL MAP LAYOUT",
                )

        # -------------------------------------------------
        # MAP STATE (EVERY ITERATION)
        # -------------------------------------------------
        elif event_type == "MAP_STATE":
            self._render_map(
                payload.get("game_map"),
                payload.get("units", []),
                title=f"MAP STATE — TURN {payload.get('turn')}",
            )

        elif event_type == "UNIT_LOADED":
            print(
                f"[UNIT] {self._unit_label(payload.get('unit_id'), payload.get('hp'))} "
                f"side={payload.get('side')} "
                f"pos={payload.get('position')}"
            )

        elif event_type == "UNIT_REMOVED":
            print(
                f"  ☠️ UNIT REMOVED: {payload.get('unit_id')} "
                f"({payload.get('reason')})"
            )

        # -------------------------------------------------
        # Actions
        # -------------------------------------------------
        elif event_type == "ACTION":
            self.current_turn = payload.get("turn")
            print(
                f"\n[TURN {self.current_turn}] "
                f"{self._unit_label(payload.get('active_unit'), payload.get('hp'))} -> "
                f"{payload.get('action')}"
            )

        # -------------------------------------------------
        # Movement / HP
        # -------------------------------------------------
        elif event_type == "ACTION_EFFECT":
            unit_id = payload.get("unit_id")
            hp_before = payload.get("hp_before")
            hp_after = payload.get("hp_after")

            if payload.get("moved"):
                print(
                    f"  🧭 MOVE {self._unit_label(unit_id, hp_after)}: "
                    f"{payload.get('from')} → {payload.get('to')} "
                    f"({payload.get('direction')})"
                )

            if hp_before != hp_after:
                print(
                    f"  ❤️ HP {unit_id}: "
                    f"{hp_before} → {hp_after} {self._hearts(hp_after)}"
                )

        # -------------------------------------------------
        # Turn end
        # -------------------------------------------------
        elif event_type == "TURN_STATE":
            print(
                f"[END TURN {payload.get('turn')}] "
                f"next active={payload.get('active_unit')}"
            )

        # -------------------------------------------------
        # CLOSE COMBAT ROUNDS
        # -------------------------------------------------
        elif event_type == "CLOSE_COMBAT_ROUND":
            atk_id = payload.get("attacker_id")
            def_id = payload.get("defender_id")

            atk_hp_after = payload.get("attacker_hp_after")
            def_hp_after = payload.get("defender_hp_after")

            print(
                f"  ⚔️  CC ROUND {payload.get('round')} "
                f"[{atk_id} vs {def_id}]"
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

            print(f"    ATK {self._unit_label(atk_id, atk_hp_after)}")
            print(f"    DEF {self._unit_label(def_id, def_hp_after)}")

        # -------------------------------------------------
        # CLOSE COMBAT RESULT
        # -------------------------------------------------
        elif event_type == "CLOSE_COMBAT_END":
            atk_id = payload.get("attacker_id")
            def_id = payload.get("defender_id")
            winner = payload.get("winner")
            outcome = payload.get("outcome")

            if outcome == "MUTUAL_DESTRUCTION":
                print(
                    f"  💥 MUTUAL DESTRUCTION [{atk_id} vs {def_id}] "
                    f"→ both units eliminated"
                )
            else:
                print(
                    f"  🏁 CC END [{atk_id} vs {def_id}] "
                    f"winner={winner} ({outcome})"
                )

        # -------------------------------------------------
        # ✅ MATCH END — PREMIO BONITO 🎉
        # -------------------------------------------------
        elif event_type == "MATCH_END":
            winner = payload.get("winner")
            reason = payload.get("reason")

            print("\n" + "=" * 40)
            print("🏆🏆🏆   MATCH FINISHED   🏆🏆🏆")
            print("=" * 40)
            print(f"🎖️  WINNER: {winner}")
            print(f"📜  Reason: {reason}")
            print("🔥  Last side standing!")
            print("=" * 40 + "\n")

        # -------------------------------------------------
        # Assault without combat
        # -------------------------------------------------
        elif event_type == "ASSAULT_NO_COMBAT":
            print(
                f"  🚫 ASSAULT NO COMBAT for {payload.get('unit_id')} "
                f"({payload.get('reason')})"
            )