from stable_baselines3 import PPO

from assault_env.env import AssaultEnv
from assault_env.agents.heuristic import HeuristicAgent


N_EPISODES = 50


def evaluate():
    env = AssaultEnv()

    ppo = PPO.load(
        "models/solved/ppo_assault_level2_solved",
        env=env,
    )

    heuristic = HeuristicAgent()

    ppo_wins = 0
    heuristic_wins = 0

    for ep in range(N_EPISODES):
        obs, _ = env.reset()
        done = False

        # PPO always starts (player A)
        current = "ppo"

        while not done:
            if current == "ppo":
                action, _ = ppo.predict(obs, deterministic=True)
            else:
                action = heuristic.act(obs)

            obs, reward, terminated, truncated, _ = env.step(action)
            done = terminated or truncated

            # Switch player turn
            current = "heuristic" if current == "ppo" else "ppo"

        # Winner determined by last reward
        if reward > 0:
            ppo_wins += 1
        else:
            heuristic_wins += 1

        print(f"Episode {ep+1}: winner = {'PPO' if reward > 0 else 'Heuristic'}")

    print("\n=== RESULTS ===")
    print(f"PPO wins: {ppo_wins}/{N_EPISODES}")
    print(f"Heuristic wins: {heuristic_wins}/{N_EPISODES}")


if __name__ == "__main__":
    evaluate()