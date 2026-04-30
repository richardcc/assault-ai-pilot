from assault_model.actions.action_catalog import ActionCatalog


class NoOpHeuristic:
    """
    NO-OP policy: always returns STATUS / WAIT.
    """

    def choose_action(self, state):
        actions = ActionCatalog(state).actions()

        for a in actions:
            if a.action_type.category.name == "STATUS":
                return a

        return actions[0] if actions else None