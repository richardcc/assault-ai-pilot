from stable_baselines3 import PPO
from assault_env.env import AssaultEnv
from assault_env.scenario_base import simple_duel_level7_P2_from_json


def run_eval(episodes=5):
    env = AssaultEnv(
        scenario_builder=simple_duel_level7_P2_from_json,
        training=False,
        max_turns=200,
    )

    model = PPO.load("models/ppo_level7_p2_current")

    for ep in range(episodes):
        obs, _ = env.reset()
        done = False
        truncated = False

        print(f"\n=== EPISODE {ep + 1} ===")

        while not (done or truncated):
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, done, truncated, info = env.step(action)

        print("Metrics:", info.get("metrics", {}))


if __name__ == "__main__":
    run_eval(episodes=5)