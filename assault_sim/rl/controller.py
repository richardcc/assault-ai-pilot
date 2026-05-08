# assault_sim/rl/controller.py

import torch
import torch.distributions as dist

from assault_model.actions.action_catalog import ActionCatalog


class RLPolicyController:
    """
    RL Controller for actor-critic / PPO.

    Responsibilities:
    - Use RL observation vector (obs) to sample actions
    - Use GameState ONLY to query legal actions
    - Store PPO-related tensors for training
    """

    def __init__(self, policy_net, rl_side=None, max_turns=None):
        self.policy = policy_net
        self.rl_side = rl_side
        self.max_turns = max_turns

        # PPO bookkeeping
        self.last_rl_action = False
        self.last_action_index = None
        self.last_log_prob = None
        self.last_value = None

    def choose_action(self, game_state, obs):
        """
        Parameters
        ----------
        game_state : GameState
            Full simulator state (used to get legal actions)

        obs : np.ndarray
            RL observation vector (already encoded)
        """

        # Reset flag
        self.last_rl_action = False

        # Fetch legal actions from simulator
        actions = ActionCatalog(game_state).actions()
        if not actions:
            self.last_action_index = None
            self.last_log_prob = None
            self.last_value = None
            return None

        # Forward pass through policy
        obs_t = torch.tensor(obs, dtype=torch.float32).unsqueeze(0)
        logits, value = self.policy(obs_t)

        # Restrict logits to legal actions only
        logits = logits[0][: len(actions)]
        value = value.squeeze(0)

        dist_action = dist.Categorical(logits=logits)
        action_idx = dist_action.sample()

        # Store PPO data
        self.last_action_index = action_idx.item()
        self.last_log_prob = dist_action.log_prob(action_idx)
        self.last_value = value
        self.last_rl_action = True

        return actions[self.last_action_index]