# assault_model/core/game_state_reactions.py
"""
GameStateReactions manages reaction-related state and resolution.

Scope:
- Track reaction-capable units
- Store reaction-specific state
- Resolve triggered reactions (e.g. overwatch)

Responsibilities:
- Maintain reaction registries
- Evaluate reaction triggers
- Apply reaction effects via the main engine

Non-responsibilities:
- Does NOT control unit activation
- Does NOT start or end turns
- Does NOT select actions
- Does NOT decide primary game flow

Design rule:
- Reactions are consequences, never drivers, of the main game loop.
"""
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