class PPOConfig:
    RL_SIDE = "US"

    TOTAL_UPDATES = 4000

    # PPO
    ROLLOUT_STEPS = 192        # ✅ más contexto (mejor decisiones)
    PPO_EPOCHS = 3             # ✅ aprende mejor de cada batch
    CLIP_EPS = 0.1

    # Discounting
    GAMMA = 0.99
    LAMBDA = 0.95

    # Loss
    VALUE_COEF = 0.5
    ENTROPY_COEF = 0.05        # 👇 lo bajamos dinámico luego

    # Parallelism
    NUM_ENVS = 20
    BATCH_ROLLOUTS = 4

    # Optimizer
    LR = 8e-5