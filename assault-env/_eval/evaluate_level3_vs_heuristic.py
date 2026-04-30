from stable_baselines3 import PPO
from assault_env.env import AssaultEnv
from assault_env.agents.heuristic import HeuristicAgent


N_EPISODES = 50


def evaluate():
    env = AssaultEnv()

    model = PPO.load(
        "models/ppo_level6_current",
        env=env,
    )

    heuristic = HeuristicAgent()

    ppo_wins = 0
    heuristic_wins = 0

    action_counts = {
        "WAIT": 0,
        "MOVE": 0,
        "ASSAULT": 0,
        "RANGED_FIRE": 0,
    }

    for ep in range(N_EPISODES):
        obs, _ = env.reset()
        done = False
        current = "ppo"  # PPO always starts

        while not done:
            if current == "ppo":
                action, _ = model.predict(obs, deterministic=True)
                action_counts[
                    ["WAIT", "MOVE", "ASSAULT", "RANGED_FIRE"][action]
                ] += 1
            else:
                action = heuristic.act(obs)

            obs, reward, terminated, truncated, _ = env.step(action)
            done = terminated or truncated
            current = "heuristic" if current == "ppo" else "ppo"

        if reward > 0:
            ppo_wins += 1
        else:
            heuristic_wins += 1

        print(
            f"Episode {ep+1:02d}: "
            f"{'PPO' if reward > 0 else 'Heuristic'} wins"
        )

    print("\n=== RESULTS: LEVEL 3b vs HEURISTIC ===")
    print(f"PPO wins:        {ppo_wins}/{N_EPISODES}")
    print(f"Heuristic wins:  {heuristic_wins}/{N_EPISODES}")

    print("\nPPO action usage:")
    total = sum(action_counts.values())
    for k, v in action_counts.items():
        pct = 100 * v / total if total > 0 else 0
        print(f"  {k:12s}: {v:4d} ({pct:5.1f}%)")


if __name__ == "__main__":
    evaluate()
