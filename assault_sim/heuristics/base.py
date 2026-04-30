class BasicHeuristic:
    """
    Phase 1 heuristic.
    Minimal functional decision logic.
    """

    def choose_action(self, state, knowledge=None, strategy=None):
        actions = state.available_actions()
        if not actions:
            return None

        # 1) Prefer combat
        for action in actions:
            if action.action_type.category.name == "COMBAT":
                return action

        # 2) Otherwise move
        for action in actions:
            if action.action_type.category.name == "MOVEMENT":
                return action

        # 3) Otherwise wait/status
        for action in actions:
            if action.action_type.category.name == "STATUS":
                return action

        return actions[0]