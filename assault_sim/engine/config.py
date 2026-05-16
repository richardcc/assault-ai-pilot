class PPOConfig:
    TOTAL_EPISODES = 6000

    ROLLOUT_STEPS = 128       # ✅ más estable
    PPO_EPOCHS = 3            # ✅ menos overfitting por batch

    CLIP_EPS = 0.05           # ✅ clave (antes 0.15)
    GAMMA = 0.99
    LAMBDA = 0.95

    VALUE_COEF = 0.5

    ENTROPY_COEF = 0.003      # ✅ MUY IMPORTANTE (antes 0.03)