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

from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic

# combate
from assault_model.actions.movement import MoveAction
from assault_model.actions.ranged_direct import RangedDirectAttack


# -------------------------------------------------
# CONFIG
# -------------------------------------------------
EPISODES = 50
MAX_STEPS = 200
RL_SIDE = "US"


def main():
    print(">>> PPO evaluation started")

    # -------------------------------------------------
    # LOAD MODEL
    # -------------------------------------------------
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

    option_policy = OptionPolicy(policy)
    heuristic = TacticalPathHeuristic()
    option_executor = OptionExecutor(heuristic)

    hrl_controller = HRLController(
        option_policy=option_policy,
        option_executor=option_executor,
        rl_side=RL_SIDE,
    )

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
    wins = 0
    vp_scores = []
    steps_list = []

    # ✅ tipos de combate
    ranged_count = 0
    melee_attempts = 0

    # -------------------------------------------------
    # EPISODES
    # -------------------------------------------------
    for ep in range(EPISODES):
        obs = env.reset()

        done = False
        steps = 0

        while not done:
            state = env.state
            active = state.active_unit

            if active is None:
                action = None
            elif active.side == RL_SIDE:
                action = hrl_controller.choose_action(state, obs)
            else:
                action = heuristic.choose_action(state)

            # ✅ guardamos state antes de step (clave)
            prev_state = state

            obs, reward, done, info = env.step(action)

            # -------------------------------------------------
            # ✅ DETECCIÓN TIPOS COMBATE (CORRECTA)
            # -------------------------------------------------
            if action is not None:

                # ---------- RANGED ----------
                if isinstance(action, RangedDirectAttack):
                    ranged_count += 1

                # ---------- MELEE ----------
                elif isinstance(action, MoveAction):

                    path = getattr(action, "path", None)
                    if path:
                        dest = path[-1]

                        # comprobar si destino tenía enemigo
                        for u in prev_state.units:
                            if u.side != active.side and u.alive:
                                if u.position == dest:
                                    melee_attempts += 1
                                    break

            steps += 1

            if steps >= MAX_STEPS:
                print(f"⚠️ Forced stop ep={ep}")
                break

        # -------------------------------------------------
        # RESULTADOS
        # -------------------------------------------------
        state = env.state

        winner = state.winner
        reason = state.end_reason
        vp = state.vp_tracker.total_points if state.vp_tracker else 0

        if winner == RL_SIDE:
            wins += 1

        vp_scores.append(vp)
        steps_list.append(steps)

        print(
            f"[EP {ep}] winner={winner} reason={reason} "
            f"VP={vp} steps={steps}"
        )

    # -------------------------------------------------
    # SUMMARY
    # -------------------------------------------------
    print("\n=== RESULTS ===")
    print(f"Episodes:   {EPISODES}")
    print(f"Win rate:   {wins / EPISODES:.2%}")
    print(f"Avg VP:     {statistics.mean(vp_scores):.2f}")
    print(f"Avg steps:  {statistics.mean(steps_list):.1f}")

    # -------------------------------------------------
    # ✅ TIPOS DE COMBATE
    # -------------------------------------------------
    print("\n=== COMBAT TYPES ===")
    print(f"Ranged attacks: {ranged_count}")
    print(f"Melee attempts: {melee_attempts}")

    total = ranged_count + melee_attempts
    if total > 0:
        ratio = melee_attempts / total
        print(f"Melee ratio: {ratio:.2%}")

    print("================")

    print("\n>>> Evaluation finished")


if __name__ == "__main__":
    main()