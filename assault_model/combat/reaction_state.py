# assault_model/combat/reaction_state.py
class ReactionState:
    def __init__(self):
        self.available: bool = True

    def consume(self):
        self.available = False

    def reset(self):
        self.available = True