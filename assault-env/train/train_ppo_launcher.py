import os
import torch
import time

from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv
from stable_baselines3.common.logger import configure

from assault_env.env import AssaultEnv


def make_env():
    # ✅ EXPLICIT TRAINING MODE
    return AssaultEnv(training=True)


if __name__ == "__main__":
    RUN_ID = "current"
    LOG_DIR = f"logs/ppo_level7/{RUN_ID}"
    os.makedirs(LOG_DIR, exist_ok=True)

    print("=== PPO TRAIN LAUNCHER ===", flush=True)
    print("CUDA available:", torch.cuda.is_available(), flush=True)
    print("Log dir:", os.path.abspath(LOG_DIR), flush=True)
    print("==========================", flush=True)

    env = DummyVecEnv([make_env])

    logger = configure(LOG_DIR, ["stdout", "tensorboard"])

    model = PPO(
        policy="MultiInputPolicy",
        env=env,
        device="cuda" if torch.cuda.is_available() else "cpu",
        verbose=2,
        n_steps=256,
        batch_size=64,
        n_epochs=4,
        gamma=0.99,
        gae_lambda=0.95,
        clip_range=0.2,
        ent_coef=0.01,
    )

    model.set_logger(logger)

    TOTAL_STEPS = 200_000

    start_time = time.time()
    try:
        model.learn(total_timesteps=TOTAL_STEPS)
    except KeyboardInterrupt:
        print("\nTraining interrupted by user (Ctrl+C)", flush=True)
    finally:
        elapsed = time.time() - start_time
        print(f"Training stopped after {elapsed:.1f}s", flush=True)

        os.makedirs("models", exist_ok=True)
        model_path = f"models/ppo_level7_{RUN_ID}"
        model.save(model_path)
        print("Model saved to:", model_path, flush=True)