class PPOConfig:
    RL_SIDE = "US"

    TOTAL_UPDATES = 4000

    # PPO
    ROLLOUT_STEPS = 256
    PPO_EPOCHS = 3
    CLIP_EPS = 0.1

    # Discounting
    GAMMA = 0.99
    LAMBDA = 0.95

    # Loss
    VALUE_COEF = 0.5
    ENTROPY_COEF = 0.02

    # Parallelism
    NUM_ENVS = 32
    BATCH_ROLLOUTS = 20

    # Optimizer
    LR = 3e-4