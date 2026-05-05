# assault_sim/debug/combat_renderer.py

class CombatRenderer:
    """
    CombatRenderer

    Responsibility:
    - Render Close Combat ACTION_EFFECT events in a human-readable way.
    - Display all combat rounds.
    - Display dice and HP changes per round.
    - Display final outcome.

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

    def __init__(self, turn_buffer):
        self.turn_buffer = turn_buffer

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
            self.turn_buffer.add_line(
                f"             Round {r['round']}"
            )

            # Dice blocks
            self._render_dice_line(
                "Attacker attack",
                r.get("attacker_attack_dice", [])
            )
            self._render_dice_line(
                "Attacker defense",
                r.get("attacker_defense_dice", [])
            )
            self._render_dice_line(
                "Defender attack",
                r.get("defender_attack_dice", [])
            )
            self._render_dice_line(
                "Defender defense",
                r.get("defender_defense_dice", [])
            )

            # Damage block
            atk_before = r.get("attacker_hp_before")
            atk_after = r.get("attacker_hp_after")
            def_before = r.get("defender_hp_before")
            def_after = r.get("defender_hp_after")

            if None not in (atk_before, atk_after, def_before, def_after):
                atk_delta = atk_before - atk_after
                def_delta = def_before - def_after

                self.turn_buffer.add_line("                 Damage this round:")

                if atk_delta > 0:
                    self.turn_buffer.add_line(
                        f"                     {self.turn_buffer.unit_label(attacker_id)}: "
                        f"-{atk_delta} HP ({atk_before} → {atk_after})"
                    )

                if def_delta > 0:
                    self.turn_buffer.add_line(
                        f"                     {self.turn_buffer.unit_label(defender_id)}: "
                        f"-{def_delta} HP ({def_before} → {def_after})"
                    )

                if atk_delta == 0 and def_delta == 0:
                    self.turn_buffer.add_line(
                        "                     No damage applied"
                    )

        # Final outcome
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
        """
        Render a die safely.

        Supported formats:
        - ("RED", "CRITICAL")
        - {"color": "RED", "face": "CRITICAL"}
        """
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
