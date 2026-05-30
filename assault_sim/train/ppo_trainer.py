import torch
import torch.distributions as torch_dist
import torch.nn.functional as F

from assault_sim.config.ppo_config import PPOConfig


# ----------------------------------------
# ✅ GAE (CRÍTICO)
# ----------------------------------------
def compute_gae(rewards, values, dones, gamma, lam):

    advantages = []
    gae = 0

    values = list(values) + [0.0]

    for t in reversed(range(len(rewards))):
        delta = rewards[t] + gamma * values[t + 1] * (1 - dones[t]) - values[t]
        gae = delta + gamma * lam * (1 - dones[t]) * gae
        advantages.insert(0, gae)

    return advantages


# ----------------------------------------
# ✅ PPO UPDATE
# ----------------------------------------
def ppo_update(policy, optimizer, batch, schedule, device):

    update, alpha, kl_coef = schedule

    obs_t = batch["obs"]
    act_t = batch["actions"]
    attack_t = batch["attack_modes"]
    old_logp_t = batch["old_logp"]
    advantages = batch["advantages"]
    returns = batch["returns"]
    teacher_t = batch["teacher"]

    for _ in range(PPOConfig.PPO_EPOCHS):

        hidden = policy.init_hidden(obs_t.size(0), device)

        option_logits, attack_logits, values, _ = policy(obs_t, hidden)

        option_dist = torch_dist.Categorical(logits=option_logits)
        attack_dist = torch_dist.Categorical(logits=attack_logits)

        logp = (
            option_dist.log_prob(act_t)
            + attack_dist.log_prob(attack_t)
        )

        ratio = torch.exp(torch.clamp(logp - old_logp_t, -5, 5))

        clipped = torch.clamp(
            ratio,
            1 - PPOConfig.CLIP_EPS,
            1 + PPOConfig.CLIP_EPS
        )

        policy_loss = -torch.min(
            ratio * advantages,
            clipped * advantages
        ).mean()

        value_loss = (returns - values.view(-1)).pow(2).mean()

        entropy = (
            option_dist.entropy().mean()
            + 0.5 * attack_dist.entropy().mean()
        )

        loss = (
            policy_loss
            + PPOConfig.VALUE_COEF * value_loss
            - PPOConfig.ENTROPY_COEF * entropy
        )

        # ✅ KL
        kl = (old_logp_t - logp).mean()
        loss += kl_coef * kl

        # ✅ imitation
        imitation_loss = F.cross_entropy(option_logits, teacher_t)
        loss += alpha * imitation_loss

        # ✅ controlled update
        if update:
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

    return loss.item()
