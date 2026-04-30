# assault_model/core/game_state_reactions.py
from assault_model.combat.reaction_state import ReactionState
from assault_model.core.reaction_registry import ReactionRegistry


class GameStateReactions:
    def __init__(self):
        self.registry = ReactionRegistry()
        self.states: dict[str, ReactionState] = {}

    def ensure_unit(self, unit_id: str):
        if unit_id not in self.states:
            self.states[unit_id] = ReactionState()

    def reset_all(self):
        for state in self.states.values():
            state.reset()