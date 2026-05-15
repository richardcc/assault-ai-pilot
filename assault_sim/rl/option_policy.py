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

        # ✅ Detect device automatically (CPU / GPU)
        self.device = next(policy_net.parameters()).device

        # Stored for PPO
        self.last_option = None
        self.last_log_prob = None
        self.last_value = None

        # ✅ Explainability
        self.last_decision_info = None

    def choose_option(self, obs) -> TacticalOption:
        """
        Sample a tactical option from the policy network.
        """

        # -------------------------------------------------
        # ✅ CONVERT TO TENSOR + MOVE TO DEVICE
        # -------------------------------------------------
        obs = torch.as_tensor(obs, dtype=torch.float32, device=self.device)

        # ✅ Ensure batch dimension
        if obs.dim() == 1:
            obs = obs.unsqueeze(0)

        # -------------------------------------------------
        # ✅ FORWARD PASS
        # -------------------------------------------------
        logits, value = self.policy_net(obs)

        option_dist = dist.Categorical(logits=logits)
        option_index = option_dist.sample()

        # -------------------------------------------------
        # ✅ STORE PPO DATA
        # -------------------------------------------------
        self.last_option = TacticalOption(option_index.item())
        self.last_log_prob = option_dist.log_prob(option_index).detach()
        self.last_value = value.squeeze().detach()

        # -------------------------------------------------
        # ✅ EXPLAINABILITY
        # -------------------------------------------------
        with torch.no_grad():
            probs = torch.softmax(logits, dim=-1)

        self.last_decision_info = {
            "option": self.last_option.name,
            "confidence": float(probs[0, option_index].item()),
            "value_estimate": float(value.item()),
        }

        return self.last_option
