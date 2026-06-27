class TacticalService:
    """
    Tactical explanation service with no external AI dependency.
    """

    def __init__(self):
        pass

    def explain(self, activation_events):
        """
        Explain the tactical resolution of a single activation using
        a lightweight event summary.
        """
        if not activation_events:
            return {
                "facts": "The unit performed the action without any tactical resolution.",
                "rules": "No tactical rules were applied.",
            }

        event_types = []
        for event in activation_events:
            if isinstance(event, dict):
                event_type = str(event.get("type", "") or "").strip()
                if event_type:
                    event_types.append(event_type)

        facts = (
            f"Activation produced {len(activation_events)} tactical events."
            if not event_types
            else f"Activation event sequence: {', '.join(event_types[:8])}."
        )
        rules = "Tactical explanation is generated from observed event flow."

        return {
            "facts": facts,
            "rules": rules,
        }