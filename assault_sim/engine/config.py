class PPOConfig:
    TOTAL_EPISODES = 6000        # 🔥 clave
    ROLLOUT_STEPS = 256
    PPO_EPOCHS = 8
    CLIP_EPS = 0.15
    GAMMA = 0.99
    LAMBDA = 0.95
    VALUE_COEF = 0.5
    ENTROPY_COEF = 0.03          # 🔧 luego bajar a 0.01