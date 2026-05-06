# assault_sim/rl/random_controller.py
import random
from assault_model.actions.action_catalog import ActionCatalog

class RandomPolicyController:
    def choose_action(self, state):
        actions = ActionCatalog(state).actions()
        return random.choice(actions) if actions else None
