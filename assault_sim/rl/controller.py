# assault_sim/rl/controller.py

import torch
import torch.distributions as dist

from assault_model.actions.action_catalog import ActionCatalog
from assault_sim.rl.state_encoder import encode_state


class RLPolicyController:
    """
    RL Controller for actor-critic / PPO.
    Stores action index, log-prob and value for training.
    """

    def __init__(self, policy_net):
        self.policy = policy_net

        # Stored per-step (for training)
        self.last_action_index = None
        self.last_log_prob = None
        self.last_value = None

    def choose_action(self, state):
        actions = ActionCatalog(state).actions()
        if not actions:
            self.last_action_index = None
            self.last_log_prob = None
            self.last_value = None
            return None

        # Encode state
        obs = encode_state(state)
        obs_t = torch.tensor(obs, dtype=torch.float32).unsqueeze(0)

        # Forward pass
        logits, value = self.policy(obs_t)

        # Restrict to legal actions
        logits = logits[0][: len(actions)]
        value = value[0]

        # Sample stochastically
        dist_action = dist.Categorical(logits=logits)
        action_idx = dist_action.sample()

        # Store for PPO/A2C
        self.last_action_index = action_idx.item()
        self.last_log_prob = dist_action.log_prob(action_idx)
        self.last_value = value

        return actions[self.last_action_index]