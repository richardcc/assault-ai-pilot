import torch
import torch.distributions as torch_dist
import torch.nn.functional as F
import numpy as np

from assault_sim.config.ppo_config import PPOConfig


# ----------------------------------------
# ✅ GAE
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
def _build_sequences(batch, seq_len):
    total = batch["obs"].shape[0]
    usable = (total // seq_len) * seq_len
    if usable <= 0:
        return None

    def reshape(x):
        x = x[:usable]
        return x.reshape(-1, seq_len, *x.shape[1:])

    seq = {
        "obs": reshape(batch["obs"]),
        "actions": reshape(batch["actions"]),
        "attack_modes": reshape(batch["attack_modes"]),
        "old_logp": reshape(batch["old_logp"]),
        "advantages": reshape(batch["advantages"]),
        "returns": reshape(batch["returns"]),
        "teacher": reshape(batch["teacher"]),
        "dones": reshape(batch["dones"]),
    }

    # Scalars may arrive as [..., 1] (e.g. stacked logp/value buffers).
    # PPO math below expects [B, T] for scalar trajectories.
    for k in ("actions", "attack_modes", "old_logp", "advantages", "returns", "teacher", "dones"):
        if seq[k].dim() == 3 and seq[k].shape[-1] == 1:
            seq[k] = seq[k].squeeze(-1)

    return seq


def ppo_update(policy, optimizer, batch, schedule, device, entropy_coef):

    update, alpha, kl_coef = schedule
    for key, tensor in batch.items():
        if isinstance(tensor, torch.Tensor) and not torch.isfinite(tensor).all():
            raise ValueError(f"Non-finite values detected in batch['{key}']")

    seq_batch = _build_sequences(batch, PPOConfig.SEQ_LEN)
    if seq_batch is None:
        return {
            "loss": 0.0,
            "policy_loss": 0.0,
            "value_loss": 0.0,
            "entropy": 0.0,
            "approx_kl": 0.0,
            "clip_fraction": 0.0,
            "imitation_loss": 0.0,
            "grad_norm": 0.0,
            "samples_used": 0,
        }

    obs_t = seq_batch["obs"]
    act_t = seq_batch["actions"]
    attack_t = seq_batch["attack_modes"]
    old_logp_t = seq_batch["old_logp"]
    advantages = seq_batch["advantages"]
    returns = seq_batch["returns"]
    teacher_t = seq_batch["teacher"]
    dones_t = seq_batch["dones"]

    total_seqs, tlen, _ = obs_t.shape
    mb_seqs = max(1, min(PPOConfig.MINIBATCH_SEQS, total_seqs))
    metrics = {
        "loss": [],
        "policy_loss": [],
        "value_loss": [],
        "entropy": [],
        "approx_kl": [],
        "clip_fraction": [],
        "imitation_loss": [],
        "grad_norm": [],
    }

    for _ in range(PPOConfig.PPO_EPOCHS):
        perm = torch.randperm(total_seqs, device=device)
        for start in range(0, total_seqs, mb_seqs):
            idx = perm[start:start + mb_seqs]
            obs_mb = obs_t[idx]
            act_mb = act_t[idx]
            attack_mb = attack_t[idx]
            old_logp_mb = old_logp_t[idx]
            adv_mb = advantages[idx]
            ret_mb = returns[idx]
            teacher_mb = teacher_t[idx]
            dones_mb = dones_t[idx]

            bsz = obs_mb.shape[0]
            hidden = policy.init_hidden(bsz, device)

            logits_steps = []
            attack_steps = []
            values_steps = []

            for t in range(tlen):
                step_obs = obs_mb[:, t, :]
                option_logits_t, attack_logits_t, values_t, hidden = policy(step_obs, hidden)
                logits_steps.append(option_logits_t)
                attack_steps.append(attack_logits_t)
                values_steps.append(values_t)

                if t < tlen - 1:
                    done_mask = (1.0 - dones_mb[:, t]).view(1, bsz, 1)
                    hidden = (hidden[0] * done_mask, hidden[1] * done_mask)

            option_logits = torch.stack(logits_steps, dim=1)
            attack_logits = torch.stack(attack_steps, dim=1)
            values = torch.stack(values_steps, dim=1)

            option_dist = torch_dist.Categorical(logits=option_logits)
            attack_dist = torch_dist.Categorical(logits=attack_logits)

            logp = option_dist.log_prob(act_mb) + attack_dist.log_prob(attack_mb)
            ratio = torch.exp(torch.clamp(logp - old_logp_mb, -5, 5))
            clipped = torch.clamp(ratio, 1 - PPOConfig.CLIP_EPS, 1 + PPOConfig.CLIP_EPS)

            policy_loss = -torch.min(ratio * adv_mb, clipped * adv_mb).mean()
            value_loss = (ret_mb - values).pow(2).mean()
            entropy_option = option_dist.entropy().mean()
            entropy_attack = attack_dist.entropy().mean()
            entropy = entropy_option + 0.5 * entropy_attack

            kl = (old_logp_mb - logp).mean()
            imitation_loss = F.cross_entropy(
                option_logits.reshape(-1, option_logits.shape[-1]),
                teacher_mb.reshape(-1),
            )

            loss = (
                policy_loss
                + PPOConfig.VALUE_COEF * value_loss
                - entropy_coef * entropy
                + kl_coef * kl
                + alpha * imitation_loss
            )
            if not torch.isfinite(loss):
                raise ValueError("Non-finite PPO loss detected")

            clip_fraction = ((ratio > 1 + PPOConfig.CLIP_EPS) | (ratio < 1 - PPOConfig.CLIP_EPS)).float().mean()
            approx_kl = kl.detach().item()

            grad_norm = 0.0
            if update and approx_kl <= PPOConfig.MAX_KL:
                optimizer.zero_grad()
                try:
                    loss.backward()
                    grad_norm = float(torch.nn.utils.clip_grad_norm_(policy.parameters(), 0.5))
                    optimizer.step()
                except RuntimeError as e:
                    if "out of memory" in str(e).lower():
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                        continue
                    raise

            metrics["loss"].append(loss.detach().item())
            metrics["policy_loss"].append(policy_loss.detach().item())
            metrics["value_loss"].append(value_loss.detach().item())
            metrics["entropy"].append(entropy.detach().item())
            metrics["approx_kl"].append(approx_kl)
            metrics["clip_fraction"].append(clip_fraction.detach().item())
            metrics["imitation_loss"].append(imitation_loss.detach().item())
            metrics["grad_norm"].append(grad_norm)

    out = {k: float(np.mean(v)) if v else 0.0 for k, v in metrics.items()}
    out["samples_used"] = int(total_seqs * tlen)
    return out