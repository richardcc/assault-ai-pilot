from stable_baselines3 import PPO
from assault_env.env import AssaultEnv


if __name__ == "__main__":
    env = AssaultEnv()
    model = PPO.load(
        "models/solved/ppo_assault_level1_solved",
        env=env,
    )

    obs, _ = env.reset()
    done = False
    step = 0

    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, terminated, truncated, _ = env.step(action)
        done = terminated or truncated
        step += 1
        print(f"Step {step}: action={action}, reward={reward}")

    print("Episode finished")

