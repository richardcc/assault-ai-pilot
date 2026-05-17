import torch
import torch.distributions as dist
from assault_sim.rl.tactical_options import TacticalOption


class OptionPolicy:
    """
    High-level RL policy with LSTM memory.
    """

    def __init__(self, policy_net: torch.nn.Module):
        self.policy_net = policy_net
        self.device = next(policy_net.parameters()).device

        # LSTM hidden state
        self.hidden = None

        # PPO storage
        self.last_option = None
        self.last_attack_mode = None
        self.last_log_prob = None
        self.last_value = None

        # explainability / debug
        self.last_decision_info = None

    # -------------------------------------------------
    def reset_hidden(self):
        """Reset LSTM memory (call every env reset)"""
        self.hidden = None

    # -------------------------------------------------
    def choose_option(self, obs):

        # ✅ ensure tensor
        obs = torch.as_tensor(obs, dtype=torch.float32, device=self.device)

        if obs.dim() == 1:
            obs = obs.unsqueeze(0)

        # -------------------------------------------------
        # INIT HIDDEN
        # -------------------------------------------------
        if self.hidden is None:
            self.hidden = self.policy_net.init_hidden(
                batch_size=1,
                device=self.device
            )

        # -------------------------------------------------
        # FORWARD (WITH MEMORY)
        # -------------------------------------------------
        option_logits, attack_logits, value, self.hidden = self.policy_net(
            obs,
            self.hidden
        )

        # ✅ CRITICAL: detach LSTM between steps
        self.hidden = (
            self.hidden[0].detach(),
            self.hidden[1].detach()
        )

        # -------------------------------------------------
        # OPTION SAMPLING
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

            attack_dist = dist.Categorical(logits=attack_logits)

            # ✅ IMPORTANT: controlled exploration (unlocks indirect & melee)
            if torch.rand(1).item() < 0.25:
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
        self.last_value = value.view(-1).detach()

        # -------------------------------------------------
        # EXPLAINABILITY (DEBUG)
        # -------------------------------------------------
        with torch.no_grad():
            option_probs = torch.softmax(option_logits, dim=-1)

        # ✅ support more attack modes (future-proof)
        mode_name = None
        if attack_mode is not None:
            if attack_mode == 0:
                mode_name = "DIRECT"
            elif attack_mode == 1:
                mode_name = "INDIRECT"
            elif attack_mode == 2:
                mode_name = "CLOSE"
            else:
                mode_name = f"MODE_{attack_mode}"

        self.last_decision_info = {
            "option": option.name,
            "attack_mode": mode_name,
            "confidence": float(option_probs[0, option_index].item()),
            "value_estimate": float(value.item()),
        }

        return option, attack_mode