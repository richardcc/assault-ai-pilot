from assault_env.env import AssaultEnv
from assault_env.renderer import AsciiRenderer
from assault_env.agents.heuristic import HeuristicAgent

from assault.replay.snapshot import snapshot
from assault.replay.replay import Replay
from assault.replay.serialization import save_replay_to_json


def run_episode():
    env = AssaultEnv()
    renderer = AsciiRenderer()
    agent = HeuristicAgent()

    replay_states = []

    # Gym reset
    obs, info = env.reset()
    turn = 0
    done = False

    # Capture initial state
    replay_states.append(snapshot(env.state))

    print("Initial observation (player A starts):", obs)
    renderer.render(env.state, env.player_id, env.enemy_id, turn=turn)

    while not done:
        action = agent.act(obs)

        obs, reward, terminated, truncated, info = env.step(action)
        done = terminated or truncated
        turn += 1

        replay_states.append(snapshot(env.state))

        print(
            f"\nTurn {turn} | "
            f"Current player = {env.current_player_id} | "
            f"Action = {action} | "
            f"Reward = {reward}"
        )

        renderer.render(env.state, env.player_id, env.enemy_id, turn=turn)

    print("\nEpisode finished")

    replay = Replay(replay_states)
    save_replay_to_json(replay, "replays/simple_duel_run_001.json")
    print("Replay saved to replays/simple_duel_run_001.json")


if __name__ == "__main__":
    run_episode()