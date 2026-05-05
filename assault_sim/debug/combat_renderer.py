# assault_sim/debug/combat_renderer.py

from assault_model.combat.dice_face import DiceFace


class CombatRenderer:
    """
    CombatRenderer

    Responsibility:
    - Render Close Combat ACTION_EFFECT events in a human-readable way.
    - Display attacker and defender with color and current HP.
    - Display combat dice with correct faces and colors.
    - Display final outcome.

    Design rules:
    - Presentation only (NO game logic).
    - Trusts resolver-emitted payloads (flat, explicit).
    - Uses TurnBuffer for consistent unit formatting.
    """

    def __init__(self, turn_buffer):
        self.turn_buffer = turn_buffer

    # -------------------------------------------------
    # EVENT HANDLER
    # -------------------------------------------------
    def on_close_combat_effect(self, payload: dict) -> None:
        """
        Handle ACTION_EFFECT with action == 'CloseCombat'.

        Expected payload (subset):
        {
            "attacker": str,
            "defender": str,
            "attacker_attack_dice": [str],
            "attacker_defense_dice": [str],
            "defender_attack_dice": [str],
            "defender_defense_dice": [str],
            "outcome": str,
            "winner": str | None,
        }
        """

        # Header
        self.turn_buffer.add_line("         💥 COMBAT")

        attacker_id = payload.get("attacker")
        defender_id = payload.get("defender")

        if attacker_id and defender_id:
            atk_label = self.turn_buffer.unit_label(attacker_id)
            def_label = self.turn_buffer.unit_label(defender_id)
            self.turn_buffer.add_line(
                f"             {atk_label} vs {def_label}"
            )

        # -------------------------------------------------
        # Attacker dice
        # -------------------------------------------------
        atk_attack = payload.get("attacker_attack_dice", [])
        if atk_attack:
            dice = " ".join(
                self._die(DiceFace[d], attacker_id)
                for d in atk_attack
            )
            self.turn_buffer.add_line(
                f"             Attack:  {dice}"
            )

        # -------------------------------------------------
        # Defender dice
        # -------------------------------------------------
        def_defense = payload.get("defender_defense_dice", [])
        if def_defense:
            dice = " ".join(
                self._die(DiceFace[d], defender_id)
                for d in def_defense
            )
            self.turn_buffer.add_line(
                f"             Defense: {dice}"
            )

        # -------------------------------------------------
        # Outcome
        # -------------------------------------------------
        outcome = payload.get("outcome")
        if outcome:
            self.turn_buffer.add_line(
                f"             Result: {outcome}"
            )

    # -------------------------------------------------
    # INTERNAL HELPERS
    # -------------------------------------------------
    def _die(self, face: DiceFace, unit_id: str) -> str:
        """
        Render a die face with the color of the owning unit.
        """
        color = "🔵" if unit_id.startswith("GE") else "🔴"
        icon = {
            DiceFace.CRITICAL: "💥",
            DiceFace.DAMAGE: "❤️",
            DiceFace.SUPPRESS: "😵",
            DiceFace.BLANK: "⚪",
        }.get(face, "?")

        return f"{color}{icon}"