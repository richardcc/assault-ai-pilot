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

        # ✅ robust tensor conversion (NO rompe grad / device)
        obs = torch.as_tensor(obs, dtype=torch.float32)

        # ✅ asegurar dimensión batch (CRÍTICO para redes)
        if obs.dim() == 1:
            obs = obs.unsqueeze(0)

        logits, value = self.policy_net(obs)

        option_dist = dist.Categorical(logits=logits)
        option_index = option_dist.sample()

        # ✅ guardar opción como enum
        self.last_option = TacticalOption(option_index.item())

        # ✅ PPO data
        self.last_log_prob = option_dist.log_prob(option_index)
        self.last_value = value.squeeze()

        # --------------------------------------------
        # ✅ CAPTURE EXPLAINABLE DECISION METADATA
        # --------------------------------------------
        with torch.no_grad():
            probs = torch.softmax(logits, dim=-1)

        self.last_decision_info = {
            "option": self.last_option.name,            # semantic, stable
            "confidence": float(probs[0, option_index]),  # ✅ FIX batch-safe
            "value_estimate": float(value.item()),      # strategic value
        }

        return self.last_option