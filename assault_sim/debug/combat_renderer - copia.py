# assault_sim/debug/combat_renderer.py

class CombatRenderer:
    """
    CombatRenderer

    Responsibility:
    - Render Close Combat ACTION_EFFECT events in a human-readable way.
    - Display all combat rounds.
    - Display dice and HP changes per round.
    - Keep HP visually correct BETWEEN rounds using formatter overrides.

    Design rules:
    - Presentation only (NO game logic).
    - Payload-driven.
    """

    DICE_FACE_ICON = {
        "CRITICAL": "💥",
        "DAMAGE": "❤️",
        "SUPPRESS": "😵",
        "BLANK": "⚪",
    }

    DICE_COLOR_ICON = {
        "BLUE": "🔵",
        "GREEN": "🟢",
        "YELLOW": "🟡",
        "RED": "🔴",
    }

    def __init__(self, turn_buffer, unit_formatter):
        self.turn_buffer = turn_buffer
        self.unit_formatter = unit_formatter

    # -------------------------------------------------
    # EVENT HANDLER
    # -------------------------------------------------
    def on_close_combat_effect(self, payload: dict) -> None:

        self.turn_buffer.add_line("         💥 COMBAT")

        attacker_id = payload.get("attacker")
        defender_id = payload.get("defender")

        # Header
        if attacker_id and defender_id:
            atk_label = self.turn_buffer.unit_label(attacker_id)
            def_label = self.turn_buffer.unit_label(defender_id)
            self.turn_buffer.add_line(
                f"             {atk_label} vs {def_label}"
            )

        rounds = payload.get("rounds", [])

        for r in rounds:
            # ---------------- ROUND HEADER ----------------
            self.turn_buffer.add_line(
                f"             Round {r['round']}"
            )

            # ---------------- DICE ----------------
            self._render_dice_line(
                "Attacker attack",
                r.get("attacker_attack_dice", []),
            )
            self._render_dice_line(
                "Attacker defense",
                r.get("attacker_defense_dice", []),
            )
            self._render_dice_line(
                "Defender attack",
                r.get("defender_attack_dice", []),
            )
            self._render_dice_line(
                "Defender defense",
                r.get("defender_defense_dice", []),
            )

            # ---------------- DAMAGE ----------------
            atk_before = r.get("attacker_hp_before")
            atk_after = r.get("attacker_hp_after")
            def_before = r.get("defender_hp_before")
            def_after = r.get("defender_hp_after")

            self.turn_buffer.add_line("                 Damage this round:")

            damage_printed = False

            if atk_before is not None and atk_after is not None:
                delta = atk_before - atk_after
                if delta > 0:
                    self.turn_buffer.add_line(
                        f"                     {self.turn_buffer.unit_label(attacker_id)}: "
                        f"-{delta} HP ({atk_before} → {atk_after})"
                    )
                    damage_printed = True

            if def_before is not None and def_after is not None:
                delta = def_before - def_after
                if delta > 0:
                    self.turn_buffer.add_line(
                        f"                     {self.turn_buffer.unit_label(defender_id)}: "
                        f"-{delta} HP ({def_before} → {def_after})"
                    )
                    damage_printed = True

            if not damage_printed:
                self.turn_buffer.add_line(
                    "                     No damage applied"
                )

            # ✅ CRITICAL FIX:
            # Update visual HP for NEXT round using overrides
            if attacker_id is not None and atk_after is not None:
                self.unit_formatter.override_hp(attacker_id, atk_after)

            if defender_id is not None and def_after is not None:
                self.unit_formatter.override_hp(defender_id, def_after)

        # ---------------- FINAL OUTCOME ----------------
        outcome = payload.get("outcome")
        if outcome:
            self.turn_buffer.add_line(
                f"             Result: {outcome}"
            )

    # -------------------------------------------------
    # INTERNAL HELPERS
    # -------------------------------------------------
    def _render_dice_line(self, label: str, dice):
        if not dice:
            return

        rendered = " ".join(self._render_die(d) for d in dice)
        self.turn_buffer.add_line(
            f"                 {label}:  {rendered}"
        )

    def _render_die(self, die) -> str:
        if isinstance(die, (tuple, list)) and len(die) == 2:
            color, face = die
            return (
                self.DICE_COLOR_ICON.get(color, "❓")
                + self.DICE_FACE_ICON.get(face, "❓")
            )

        if isinstance(die, dict):
            return (
                self.DICE_COLOR_ICON.get(die.get("color"), "❓")
                + self.DICE_FACE_ICON.get(die.get("face"), "❓")
            )

        return "❓"