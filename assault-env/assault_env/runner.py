from assault_env.env import AssaultEnv
from assault_env.renderer import AsciiRenderer
from assault_env.agents.heuristic import HeuristicAgent


env = AssaultEnv()
renderer = AsciiRenderer()
agent = HeuristicAgent()

# Gym reset
obs, info = env.reset()

done = False
turn = 0

print("Initial observation (player A starts):", obs)
renderer.render(env.state, env.player_id, env.enemy_id, turn=turn)

while not done:
    # ✅ MISMO AGENTE PARA AMBOS BANDOS
    action = agent.act(obs)

    obs, reward, terminated, truncated, info = env.step(action)
    done = terminated or truncated
    turn += 1

    print(
        f"\nTurn {turn} | "
        f"Current player = {env.current_player_id} | "
        f"Action = {action} | "
        f"Reward = {reward}"
    )

    renderer.render(env.state, env.player_id, env.enemy_id, turn=turn)

print("\nEpisode finished")
