import torch
from pathlib import Path
import statistics

from assault_sim.config.config_loader import load_sim_config
from assault_sim.sim_env import SimEnv
from assault_sim.training_env import TrainingEnv

from assault_sim.rl.policy_net import PolicyNet
from assault_sim.decision.hrl_controller import HRLController
from assault_sim.decision.option_executor import OptionExecutor
from assault_sim.rl.option_policy import OptionPolicy
from assault_sim.rl.tactical_options import TacticalOption

from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic


# -------------------------------------------------
# CONFIG
# -------------------------------------------------
EPISODES = 100
MAX_STEPS = 200
RL_SIDE = "US"


# -------------------------------------------------
# MAIN
# -------------------------------------------------
def main():
    print(">>> PPO evaluation (aligned + split stats)")

    checkpoint_path = Path("assault_sim/checkpoints/ppo_US.pt")

    if not checkpoint_path.exists():
        raise FileNotFoundError(checkpoint_path)

    checkpoint = torch.load(checkpoint_path)

    policy = PolicyNet(
        input_dim=checkpoint["input_dim"],
        max_actions=checkpoint["max_actions"],
    )
    policy.load_state_dict(checkpoint["model_state_dict"])
    policy.eval()

    print("✅ Model loaded")

    # -------------------------------------------------
    # PIPELINE (igual que train)
    # -------------------------------------------------
    heuristic = TacticalPathHeuristic()

    option_policy = OptionPolicy(policy)
    option_executor_rl = OptionExecutor(heuristic)

    hrl_controller_rl = HRLController(
        option_policy=option_policy,
        option_executor=option_executor_rl,
        rl_side=RL_SIDE,
    )

    option_executor_enemy = OptionExecutor(heuristic)

    class EnemyController:
        def choose_action(self, state, obs):
            return option_executor_enemy.execute(
                state,
                TacticalOption.ATTACK
            )

    enemy_controller = EnemyController()

    # -------------------------------------------------
    # ENV
    # -------------------------------------------------
    sim_config = load_sim_config(
        Path("assault_sim/config/sim_config.yaml")
    )
    sim_config.scenario_name = "phase01_seq001_initial_contact"

    sim_env = SimEnv(sim_config, controller=None)

    env = TrainingEnv(
        sim_env,
        env_config_path=Path("assault_sim/config/env_config.json"),
        rl_side=RL_SIDE,
    )

    # -------------------------------------------------
    # STATS
    # -------------------------------------------------
    wins = 0.0
    draws = 0

    vp_scores = []
    steps_list = []

    # RL stats
    rl_ranged = 0
    rl_melee = 0
    rl_attacks = 0

    # ENEMY stats
    enemy_ranged = 0
    enemy_melee = 0
    enemy_attacks = 0

    # -------------------------------------------------
    # RUN
    # -------------------------------------------------
    for ep in range(EPISODES):
        obs = env.reset()
        done = False
        step = 0

        while not done:
            state = env.state
            active = state.active_unit if state else None

            if active is None:
                action = None

            elif active.side == RL_SIDE:
                action = hrl_controller_rl.choose_action(state, obs)

            else:
                action = enemy_controller.choose_action(state, obs)

            obs, reward, done, info = env.step(action)

            # -------------------------------------------------
            # ✅ STATS SEPARADAS
            # -------------------------------------------------
            if action is not None and active is not None:

                name = action.__class__.__name__
                is_ranged = "Ranged" in name
                is_melee = "Assault" in name or "Close" in name
                is_attack = is_ranged or is_melee

                if active.side == RL_SIDE:
                    if is_attack:
                        rl_attacks += 1
                    if is_ranged:
                        rl_ranged += 1
                    if is_melee:
                        rl_melee += 1

                else:
                    if is_attack:
                        enemy_attacks += 1
                    if is_ranged:
                        enemy_ranged += 1
                    if is_melee:
                        enemy_melee += 1

            step += 1

            if step >= MAX_STEPS:
                done = True
                break

        # -------------------------------------------------
        # RESULT
        # -------------------------------------------------
        state = env.state
        vp = state.vp_tracker.total_points if state.vp_tracker else 0

        winner = state.winner

        if winner == RL_SIDE:
            wins += 1
        elif winner is None:
            draws += 1
            wins += 0.5

        vp_scores.append(vp)
        steps_list.append(step)

        print(
            f"[EP {ep}] winner={winner} "
            f"VP={vp} steps={step}"
        )

    # -------------------------------------------------
    # SUMMARY
    # -------------------------------------------------
    print("\n=== RESULTS ===")
    print(f"Episodes:   {EPISODES}")
    print(f"Win rate:   {wins / EPISODES:.2%}")
    print(f"Draws:      {draws}")
    print(f"Avg VP:     {statistics.mean(vp_scores):.2f}")
    print(f"Avg steps:  {statistics.mean(steps_list):.1f}")

    # -------------------------------------------------
    # COMBAT (SEPARADO)
    # -------------------------------------------------
    print("\n=== RL COMBAT ===")
    print(f"Attacks: {rl_attacks}")
    print(f"Ranged:  {rl_ranged}")
    print(f"Melee:   {rl_melee}")

    if rl_attacks > 0:
        print(f"Melee ratio: {rl_melee / rl_attacks:.2%}")

    print("\n=== ENEMY COMBAT ===")
    print(f"Attacks: {enemy_attacks}")
    print(f"Ranged:  {enemy_ranged}")
    print(f"Melee:   {enemy_melee}")

    if enemy_attacks > 0:
        print(f"Melee ratio: {enemy_melee / enemy_attacks:.2%}")

    print("\n================")
    print("\n>>> Evaluation finished")


if __name__ == "__main__":
    main()
