class PPOConfig:
    RL_SIDE = "US"

    TOTAL_UPDATES = 4000

    # PPO
    ROLLOUT_STEPS = 128        # ↓ menos conservador
    PPO_EPOCHS = 4             # ↑ más aprendizaje
    CLIP_EPS = 0.2             # ↑ deja moverse

    # Discounting
    GAMMA = 0.99
    LAMBDA = 0.95

    # Loss
    VALUE_COEF = 0.5
    ENTROPY_COEF = 0.1        # 🔥 CLAVE

    # Parallelism
    NUM_ENVS = 16              # ↓ menos estabilidad, más reacción
    BATCH_ROLLOUTS = 5        # ↓

    # Optimizer
    LR = 3e-4
