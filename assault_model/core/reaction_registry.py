# assault_model/core/reaction_registry.py
from typing import Dict, List
from assault_model.combat.reaction_fire import ReactionFireAction


class ReactionRegistry:
    def __init__(self):
        self.reactions: Dict[str, List[ReactionFireAction]] = {}

    def register(self, unit_id: str, reaction: ReactionFireAction):
        self.reactions.setdefault(unit_id, []).append(reaction)

    def get_reactions(self, unit_id: str) -> list[ReactionFireAction]:
        return self.reactions.get(unit_id, [])