import torch
import torch.distributions as dist
from assault_sim.rl.tactical_options import TacticalOption


class OptionPolicy:
    """
    High-level RL policy.

    Chooses:
    - TacticalOption
    - Attack mode (if ATTACK)
    """

    def __init__(self, policy_net: torch.nn.Module):
        self.policy_net = policy_net
        self.device = next(policy_net.parameters()).device

        # PPO storage
        self.last_option = None
        self.last_attack_mode = None
        self.last_log_prob = None
        self.last_value = None

        # explainability
        self.last_decision_info = None

    # -------------------------------------------------
    def choose_option(self, obs):

        obs = torch.as_tensor(obs, dtype=torch.float32, device=self.device)

        if obs.dim() == 1:
            obs = obs.unsqueeze(0)

        # -------------------------------------------------
        # forward
        # -------------------------------------------------
        option_logits, attack_logits, value = self.policy_net(obs)

        # -------------------------------------------------
        # OPTION
        # -------------------------------------------------
        option_dist = dist.Categorical(logits=option_logits)
        option_index = option_dist.sample()

        option = TacticalOption(option_index.item())
        log_prob_option = option_dist.log_prob(option_index)

        # -------------------------------------------------
        # ATTACK MODE
        # -------------------------------------------------
        attack_mode = None
        log_prob_attack = torch.zeros_like(log_prob_option)

        if option == TacticalOption.ATTACK:

            # ✅ usar logits correctos
            attack_dist = dist.Categorical(logits=attack_logits)

            attack_index = attack_dist.sample()
            attack_mode = attack_index.item()

            log_prob_attack = attack_dist.log_prob(attack_index)

        # -------------------------------------------------
        # PPO storage
        # -------------------------------------------------
        self.last_option = option
        self.last_attack_mode = attack_mode

        # ✅ suma correcta
        self.last_log_prob = (log_prob_option + log_prob_attack).detach()
        self.last_value = value.squeeze().detach()

        # -------------------------------------------------
        # explainability
        # -------------------------------------------------
        with torch.no_grad():
            option_probs = torch.softmax(option_logits, dim=-1)

        self.last_decision_info = {
            "option": option.name,
            "attack_mode": (
                "INDIRECT" if attack_mode == 1 else "DIRECT"
                if attack_mode is not None else None
            ),
            "confidence": float(option_probs[0, option_index].item()),
            "value_estimate": float(value.item()),
        }

        return option, attack_mode