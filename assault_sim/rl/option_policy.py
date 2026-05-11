# assault_sim/rl/option_policy.py

import torch
import torch.distributions as dist
from assault_sim.rl.tactical_options import TacticalOption


class OptionPolicy:
    """
    High-level RL policy.

    Chooses a TacticalOption based on the observation.
    """

    def __init__(self, policy_net: torch.nn.Module):
        self.policy_net = policy_net

        # Stored for PPO
        self.last_option = None
        self.last_log_prob = None
        self.last_value = None

        # ✅ NEW: Stored for explanation / replay
        self.last_decision_info = None

    def choose_option(self, obs) -> TacticalOption:
        """
        Sample a tactical option from the policy network.

        This is the ONLY place where HRL decisions are made.
        """

        # ✅ ensure obs is a torch.Tensor
        if not isinstance(obs, torch.Tensor):
            obs = torch.tensor(obs, dtype=torch.float32)

        logits, value = self.policy_net(obs)

        option_dist = dist.Categorical(logits=logits)
        option_index = option_dist.sample()

        self.last_option = TacticalOption(option_index.item())
        self.last_log_prob = option_dist.log_prob(option_index)
        self.last_value = value

        # --------------------------------------------
        # ✅ CAPTURE EXPLAINABLE DECISION METADATA
        # --------------------------------------------
        with torch.no_grad():
            probs = torch.softmax(logits, dim=-1)

        self.last_decision_info = {
            "option": self.last_option.name,          # semantic, stable
            "confidence": float(probs[option_index]), # human-usable
            "value_estimate": float(value.item()),    # strategic value
        }

        return self.last_option
