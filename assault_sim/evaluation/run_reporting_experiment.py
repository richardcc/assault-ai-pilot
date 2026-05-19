import torch
from pathlib import Path

from assault_sim.config.config_loader import load_sim_config
from assault_sim.sim_env import SimEnv
from assault_sim.training_env import TrainingEnv

from assault_sim.rl.policy_net import PolicyNet
from assault_sim.rl.option_policy import OptionPolicy
from assault_sim.decision.hrl_controller import HRLController
from assault_sim.decision.option_executor import OptionExecutor
from assault_sim.rl.tactical_options import TacticalOption

from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic

from assault_sim.evaluation.logger import EvaluationLogger
from assault_sim.evaluation.csv_writer import write_csv


CHECKPOINT = Path("models/latest.pt")

RL_SIDE = "US"
N_EPISODES = 200


# -------------------------------------------------
# CONTEXT (minimal, extend later)
# -------------------------------------------------
def build_context(state, unit):
    return {
        "enemy_distance": None,
        "terrain": None,
        "hp": getattr(unit, "hp", 0),
    }


# -------------------------------------------------
# MAIN
# -------------------------------------------------
def run_experiment():

    rl_side = RL_SIDE
    enemy_side = "GE" if rl_side == "US" else "US"

    logger = EvaluationLogger("exp_hrl_v1")

    # -------------------------------------------------
    # CONFIG
    # -------------------------------------------------
    sim_config = load_sim_config(
        Path("assault_sim/config/sim_config.yaml")
    )

    sim_config.scenario_name = "phase01_seq001_initial_contact"

    # -------------------------------------------------
    # EPISODE LOOP
    # -------------------------------------------------
    for ep in range(N_EPISODES):

        print(f"--- Episode {ep+1}/{N_EPISODES}")

        sim_config.seed = 1000 + ep

        sim_env = SimEnv(
            sim_config,
            controller=None,
        )

        env = TrainingEnv(
            sim_env,
            env_config_path=Path("assault_sim/config/env_config.json"),
            rl_side=rl_side,
        )

        obs = env.reset()

        input_dim = obs.shape[0]

        # -------------------------------------------------
        # LOAD MODEL
        # -------------------------------------------------
        policy = PolicyNet(
            input_dim=input_dim,
            num_options=len(TacticalOption),
        )

        checkpoint = torch.load(CHECKPOINT, map_location="cpu")
        policy.load_state_dict(checkpoint)
        policy.eval()

        option_policy = OptionPolicy(policy)

        heuristic = TacticalPathHeuristic()
        executor = OptionExecutor(heuristic)

        hrl_controller = HRLController(
            option_policy=option_policy,
            option_executor=executor,
            rl_side=rl_side,
            event_bus=sim_env.event_bus,
        )

        # -------------------------------------------------
        # MATCH LOOP
        # -------------------------------------------------
        done = False
        turn = 0

        while not done:

            state = sim_env.game_state
            active = state.active_unit

            # ---------------- RL ----------------
            if active is not None and active.side == rl_side:

                action = hrl_controller.choose_action(state, obs)

                if action is None:
                    action = executor.execute(state, TacticalOption.ATTACK)

                # ✅ HRL payload
                hrl_payload = getattr(action, "hrl_payload", None)

                if hrl_payload:
                    context = build_context(state, active)

                    logger.log_decision(
                        episode_id=ep,
                        turn=state.turn,
                        unit_id=active.unit_id,
                        hrl_payload=hrl_payload,
                        context=context,
                    )

            # ---------------- HEURISTIC ----------------
            else:
                action = heuristic.choose_action(
                    state,
                    TacticalOption.ATTACK
                )

            # -------------------------------------------------
            # STEP (✅ FIX: result was not a dict)
            # -------------------------------------------------
            obs, reward, done, info = env.step(action)

            # -------------------------------------------------
            # OUTCOME (✅ SAFE VERSION)
            # -------------------------------------------------
            if active:
                logger.log_outcome(
                    episode_id=ep,
                    turn=state.turn,
                    unit_id=active.unit_id,
                    action=type(action).__name__,   # ✅ FIX correct
                    result=None                    # ✅ FIX: no dict here
                )

            turn += 1

        # -------------------------------------------------
        # EPISODE END
        # -------------------------------------------------
        final_state = sim_env.game_state

        vp = (
            final_state.vp_tracker.total_points
            if final_state.vp_tracker else 0
        )

        summary = {
            "winner": final_state.winner,
            "vp": vp,
            "steps": turn,
        }

        logger.log_episode(ep, summary)

    # -------------------------------------------------
    # SAVE CSV
    # -------------------------------------------------
    output_dir = Path("reports")
    output_dir.mkdir(parents=True, exist_ok=True)

    episodes_path = output_dir / "episodes.csv"
    decisions_path = output_dir / "decisions.csv"
    outcomes_path = output_dir / "outcomes.csv"

    write_csv(episodes_path, logger.episodes)
    write_csv(decisions_path, logger.decisions)
    write_csv(outcomes_path, logger.outcomes)

    print("✅ Reporting CSV generated:")
    print(f" - episodes:  {episodes_path.resolve()}")
    print(f" - decisions: {decisions_path.resolve()}")
    print(f" - outcomes:  {outcomes_path.resolve()}")


# -------------------------------------------------
if __name__ == "__main__":
    run_experiment()
