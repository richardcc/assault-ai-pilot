class HRLService:
    def explain(self, strategic_state, unit_id, action):
        """
        Local strategic explanation with no external AI dependency.
        """

        friendly = str(getattr(strategic_state, "friendly_strength", "unknown"))
        pressure = str(getattr(strategic_state, "enemy_pressure", "unknown"))
        objective = str(getattr(strategic_state, "objective_distance", "unknown"))

        option = "hold_position"
        category = "stability"
        if pressure.lower() in {"high", "very_high"}:
            option = "reduce_enemy_pressure"
            category = "survivability"
        elif objective.lower() in {"close", "very_close"} and friendly.lower() in {"high", "medium"}:
            option = "push_objective"
            category = "initiative"

        explanation = (
            f"Unit {unit_id} selected '{action}' with friendly_strength={friendly}, "
            f"enemy_pressure={pressure}, objective_distance={objective}."
        )

        return {
            "option": option,
            "category": category,
            "explanation": explanation,
        }