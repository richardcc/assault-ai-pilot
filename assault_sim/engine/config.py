class PPOConfig:
    TOTAL_EPISODES = 2000      # ✅ más experiencia real
    ROLLOUT_STEPS = 256       # ✅ correcto (no tocar)
    PPO_EPOCHS = 8            # 🔼 mejor uso de datos
    CLIP_EPS = 0.15           # 🔥 más estable (antes 0.2)
    GAMMA = 0.99              # ✅ correcto
    LAMBDA = 0.95             # ✅ correcto
    VALUE_COEF = 0.5          # ✅ balanceado
    ENTROPY_COEF = 0.03       # 🔥 clave para reducir pasividad
