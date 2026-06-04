import torch
import torch.distributions as dist
from assault_sim.rl.tactical_options import TacticalOption


class OptionPolicy:

    def __init__(self, policy_net: torch.nn.Module):
        self.policy_net = policy_net
        self.device = next(policy_net.parameters()).device

        self.hidden = None

        # PPO storage
        self.last_option = None
        self.last_attack_mode = None
        self.last_log_prob = None
        self.last_value = None

        self.last_decision_info = None
        self.last_option_logits = None
        self.last_attack_logits = None

        # ✅ configurable
        self.exploration_rate = 0.25

    # -------------------------------------------------
    def reset_hidden(self):
        self.hidden = None

    # -------------------------------------------------
    def choose_option(self, obs):

        obs = torch.as_tensor(obs, dtype=torch.float32, device=self.device)

        if obs.dim() == 1:
            obs = obs.unsqueeze(0)

        if self.hidden is None:
            self.hidden = self.policy_net.init_hidden(
                batch_size=1,
                device=self.device
            )

        option_logits, attack_logits, value, self.hidden = self.policy_net(
            obs,
            self.hidden
        )
        self.last_option_logits = option_logits.detach()
        self.last_attack_logits = attack_logits.detach()

        # ✅ cortar gradiente temporal
        self.hidden = (
            self.hidden[0].detach(),
            self.hidden[1].detach()
        )

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
        attack_mode = 0
        log_prob_attack = torch.zeros_like(log_prob_option)

        if option == TacticalOption.ATTACK:

            attack_dist = dist.Categorical(logits=attack_logits)

            if torch.rand(1).item() < self.exploration_rate:
                attack_index = torch.randint(
                    0,
                    attack_logits.shape[-1],
                    (1,),
                    device=attack_logits.device
                )
            else:
                attack_index = attack_dist.sample()

            attack_mode = attack_index.item()
            log_prob_attack = attack_dist.log_prob(attack_index)

        # -------------------------------------------------
        # PPO STORAGE
        # -------------------------------------------------
        self.last_option = option
        self.last_attack_mode = attack_mode

        self.last_log_prob = (log_prob_option + log_prob_attack).detach()
        self.last_value = value.squeeze(0).detach()

        # -------------------------------------------------
        # DEBUG
        # -------------------------------------------------
        with torch.no_grad():
            option_probs = torch.softmax(option_logits, dim=-1)

        self.last_decision_info = {
            "option": option.name,
            "attack_mode": attack_mode,
            "confidence": float(option_probs[0, option_index].item()),
            "value_estimate": float(value.item()),
        }

        # ✅ CRÍTICO
        return option, attack_mode, self.last_log_prob, self.last_value

    def log_prob_for(self, option: TacticalOption, attack_mode: int = 0):
        """
        Recompute log-prob for an externally resolved/executed option
        using the latest logits from choose_option.
        """
        if self.last_option_logits is None:
            return torch.zeros(1, dtype=torch.float32, device=self.device)

        option_dist = dist.Categorical(logits=self.last_option_logits)
        option_idx = torch.tensor([option.value], device=self.device)
        logp = option_dist.log_prob(option_idx)

        if option == TacticalOption.ATTACK and self.last_attack_logits is not None:
            attack_dist = dist.Categorical(logits=self.last_attack_logits)
            attack_idx = torch.tensor([int(attack_mode)], device=self.device)
            logp = logp + attack_dist.log_prob(attack_idx)

        return logp.detach()