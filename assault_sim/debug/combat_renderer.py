# assault_sim/debug/combat_renderer.py

class CombatRenderer:
    """
    CombatRenderer

    Responsibility:
    - Render Close Combat ACTION_EFFECT events in a human-readable way.
    - Render Ranged Combat ACTION_EFFECT events in a human-readable way.
    - Display dice and HP changes.
    - Keep HP visually correct BETWEEN rounds using formatter overrides.

    Design rules:
    - Presentation only (NO game logic).
    - Payload-driven.
    - NO legacy support.
    """

    DICE_FACE_ICON = {
        "CRITICAL": "💥",
        "DAMAGE": "❤️",
        "SUPPRESS": "😵",
    }

    DICE_COLOR_ICON = {
        "BLUE": "🔵",
        "GREEN": "🟢",
        "YELLOW": "🟡",
        "RED": "🔴",
    }

    BLANK_ICON = "⚪"

    def __init__(self, turn_buffer, unit_formatter):
        self.turn_buffer = turn_buffer
        self.unit_formatter = unit_formatter

    # -------------------------------------------------
    # GENERIC ENTRY POINT
    # -------------------------------------------------
    def on_action_effect(self, payload: dict) -> None:
        action = payload.get("action")

        if action == "CloseCombat":
            self.on_close_combat_effect(payload)
            return

        if action == "RangedCombat":
            self.on_ranged_combat_effect(payload)
            return

    # -------------------------------------------------
    # CLOSE COMBAT (UNCHANGED LOGIC, NEW RENDERING)
    # -------------------------------------------------
    def on_close_combat_effect(self, payload: dict) -> None:
        self.turn_buffer.add_line("         💥 COMBAT")

        attacker_id = payload.get("attacker")
        defender_id = payload.get("defender")

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

            if attacker_id is not None and atk_after is not None:
                self.unit_formatter.override_hp(attacker_id, atk_after)

            if defender_id is not None and def_after is not None:
                self.unit_formatter.override_hp(defender_id, def_after)

        outcome = payload.get("outcome")
        if outcome:
            self.turn_buffer.add_line(
                f"             Result: {outcome}"
            )

    # -------------------------------------------------
    # RANGED COMBAT (NEW RENDERING)
    # -------------------------------------------------
    def on_ranged_combat_effect(self, payload: dict) -> None:
        attacker_id = payload.get("attacker")
        defender_id = payload.get("defender")
        distance = payload.get("distance")
        sector = payload.get("attack_sector")

        atk_label = (
            self.turn_buffer.unit_label(attacker_id)
            if attacker_id else "?"
        )
        def_label = (
            self.turn_buffer.unit_label(defender_id)
            if defender_id else "?"
        )

        # ✅ NUEVO: detectar modo
        mode = payload.get("attack_mode", "DIRECT_FIRE")

        if mode == "INDIRECT_FIRE":
            self.turn_buffer.add_line("         🎯 RangedIndirectAttack (no LOS)")
        else:
            self.turn_buffer.add_line("         🎯 RangedDirectAttack")

        self.turn_buffer.add_line(
            f"             {atk_label} → {def_label} "
            f"(dist {distance}, sector {sector})"
        )

        self._render_dice_line(
            "Attacker attack",
            payload.get("attacker_attack_dice", []),
        )
        self._render_dice_line(
            "Defender defense",
            payload.get("defender_defense_dice", []),
        )

        hp_before = payload.get("defender_hp_before")
        hp_after = payload.get("defender_hp_after")
        if (
            defender_id
            and hp_before is not None
            and hp_after is not None
        ):
            delta = hp_before - hp_after
            if delta > 0:
                self.turn_buffer.add_line(
                    f"                 {self.turn_buffer.unit_label(defender_id)}: "
                    f"-{delta} HP ({hp_before} → {hp_after})"
                )

        criticals = payload.get("attacker_effects", {}).get("criticals", [])
        if criticals:
            self.turn_buffer.add_line(
                f"                 💥 Critical hits: {len(criticals)}"
            )

        defender_killed = payload.get("defender_killed", False)
        if defender_killed and defender_id:
            self.turn_buffer.add_line(
                f"                 ☠️ {self.turn_buffer.unit_label(defender_id)} DESTROYED"
            )

        if defender_id is not None and hp_after is not None:
            self.unit_formatter.override_hp(defender_id, hp_after)

        # ✅ SUPPRESSION
        suppression = payload.get("suppression", {})

        if suppression.get("applied"):
            self.turn_buffer.add_line(
                f"                 😵 {self.turn_buffer.unit_label(defender_id)} SUPPRESSED"
            )

    # -------------------------------------------------
    # INTERNAL HELPERS (NEW, NO LEGACY)
    # -------------------------------------------------
    def _render_dice_line(self, label: str, dice: list) -> None:
        if not dice:
            return

        rendered = " ".join(self._render_die(d) for d in dice)
        self.turn_buffer.add_line(
            f"                 {label}:  {rendered}"
        )

    def _render_die(self, die: dict) -> str:
        """
        Render a single die.

        Expected format:
        {
            "color": "RED",
            "faces": ["CRITICAL", "DAMAGE"]
        }
        """
        color_icon = self.DICE_COLOR_ICON.get(die["color"], "❓")

        faces = die.get("faces", [])
        if not faces:
            return color_icon + self.BLANK_ICON

        face_icons = "".join(
            self.DICE_FACE_ICON.get(face, "❓")
            for face in faces
        )

        return color_icon + face_icons
