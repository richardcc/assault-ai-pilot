# assault_sim/decision/side_controller.py

class SideController:
    """
    Per-side decision controller.
    Delegates the decision to the assigned policy.
    """

    def __init__(self, policy):
        self.policy = policy

    def choose_action(self, state):
        return self.policy.choose_action(state)