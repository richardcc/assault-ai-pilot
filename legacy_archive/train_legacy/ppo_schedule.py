def ppo_schedule(rollout_idx):

    update = rollout_idx >= 300

    if rollout_idx < 200:
        alpha = 1.0
    elif rollout_idx < 800:
        alpha = 0.5
    else:
        alpha = 0.2

    if rollout_idx < 300:
        kl_coef = 0.1
    else:
        kl_coef = 0.05

    return update, alpha, kl_coef