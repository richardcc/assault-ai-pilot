from stable_baselines3 import PPO

from assault_env.env import AssaultEnv
from assault_env.scenario_base import simple_duel_level7_P4_2v2_from_json


def run_eval(
    model_path: str,
    episodes: int = 10,
    deterministic: bool = True,
):
    """
    Evaluation script for P4-B (implicit roles).
    Uses the same observation space as training.

    Args:
        model_path: path to the trained PPO model
        episodes: number of evaluation episodes
        deterministic: greedy (True) or stochastic (False)
    """

    env = AssaultEnv(
        scenario_builder=simple_duel_level7_P4_2v2_from_json,
        training=False,
        max_turns=200,
    )

    model = PPO.load(model_path)

    print("\n======== EVALUATION START ========")
    print(f"Model        : {model_path}")
    print(f"Episodes     : {episodes}")
    print(f"Deterministic: {deterministic}")
    print("=================================\n")

    for ep in range(episodes):
        obs, _ = env.reset()
        terminated = False
        truncated = False

        while not (terminated or truncated):
            action, _ = model.predict(obs, deterministic=deterministic)
            obs, reward, terminated, truncated, info = env.step(action)

        print(f"=== EPISODE {ep + 1} ===")
        print("Metrics:", info.get("metrics", {}))

    print("\n========= EVALUATION END =========\n")


if __name__ == "__main__":
    # ---- CHANGE ONLY THESE VALUES ----
    MODEL_PATH = "models/ppo_level7_p4_2v2_roles"
    EPISODES = 10
    DETERMINISTIC = False   # False for non-greedy
    # ---------------------------------

    run_eval(
        model_path=MODEL_PATH,
        episodes=EPISODES,
        deterministic=DETERMINISTIC,
    )