import torch
from pathlib import Path

from assault_sim.decision.decision_engine import DecisionEngine
from assault_sim.decision.decision_engine_controller import DecisionEngineController

from assault_sim.config.config_loader import load_sim_config
from assault_sim.sim_env import SimEnv
from assault_sim.training_env import TrainingEnv

from assault_sim.rl.policy_net import PolicyNet
from assault_sim.rl.option_policy import OptionPolicy
from assault_sim.rl.tactical_options import TacticalOption

from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic

from assault_sim.engine.match_runner import MatchRunner

from assault_sim.debug.console_observer import ConsoleObserver
from assault_sim.debug.debug_config import DebugConfig

from assault_sim.debug.replay_observer import ReplayObserver
from assault_sim.debug.replay_writer import ReplayWriter
from assault_sim.debug.replay_utils import extract_initial_state


RL_SIDE = "US"
CHECKPOINT = Path("models/latest.pt")

DEBUG_L3 = False  # ✅ activar si quieres ver estrategias


# -------------------------------------------------
# MAIN
# -------------------------------------------------
def main():

    rl_side = RL_SIDE
    enemy_side = "GE" if rl_side == "US" else "US"

    print(f">>> Replaying: RL ({rl_side}) vs Heuristic ({enemy_side})")

    # -------------------------------------------------
    # ENV
    # -------------------------------------------------
    sim_config = load_sim_config(
        Path("C:/repos/python/assault/assault_sim/config/sim_config.yaml")
    )

    sim_config.scenario_name = "phase01_seq001_initial_contact"
    sim_config.seed = 42

    sim_env = SimEnv(
        sim_config,
        controller=None,
        debug_config=DebugConfig(enabled=True),
    )

    env = TrainingEnv(
        sim_env,
        env_config_path=Path("C:/repos/python/assault/assault_sim/config/env_config.json"),
        rl_side=rl_side,
    )

    obs = env.reset()
    input_dim = obs.shape[0]

    # -------------------------------------------------
    # MODEL
    # -------------------------------------------------
    print(f">>> Loading checkpoint: {CHECKPOINT}")

    policy = PolicyNet(
        input_dim=input_dim,
        num_options=len(TacticalOption),
    )

    checkpoint = torch.load(CHECKPOINT, map_location="cpu")
    policy.load_state_dict(checkpoint)
    policy.eval()

    print(">>> PPO model loaded [OK]")

    # -------------------------------------------------
    # COMPONENTES
    # -------------------------------------------------
    decision_engine = DecisionEngine()
    option_policy = OptionPolicy(policy)
    heuristic = TacticalPathHeuristic()

    controller = DecisionEngineController(
        rl_side=rl_side,
        decision_engine=decision_engine,
        option_policy=option_policy,
        heuristic=heuristic,
        sim_env=sim_env,
    )

    # ✅ modo evaluación
    controller.training_mode = False

    # ✅ reset inicial
    controller.reset()

    # -------------------------------------------------
    # OBSERVERS
    # -------------------------------------------------
    observer = ConsoleObserver(rl_side=rl_side)
    replay_observer = ReplayObserver()

    if sim_env.event_bus:
        sim_env.event_bus.subscribe(observer)
        sim_env.event_bus.subscribe(replay_observer)

    replay_observer.replay.initial_state = extract_initial_state(
        sim_env.game_state
    )

    replay_observer.replay.meta = {
        "scenario_id": sim_config.scenario_name,
        "sides": {
            rl_side: "RL",
            enemy_side: "HEURISTIC",
        },
    }

    # -------------------------------------------------
    # MATCH
    # -------------------------------------------------
    runner = MatchRunner(env, controller=controller)

    done = False
    step = 0

    while not done:
        result = runner.step(controller, obs)
        obs = result["obs"]
        done = result["done"]
        step += 1

        # ✅ DEBUG L3 (OPCIONAL)
        if DEBUG_L3:
            strat = controller.current_strategy
            opt = controller.current_option

            print(
                f"[STEP {step}] "
                f"strategy={strat.name if strat else None} "
                f"option={opt.name if opt else None}"
            )

    # -------------------------------------------------
    # RESULT
    # -------------------------------------------------
    final_state = sim_env.game_state

    vp = final_state.vp_tracker.total_points if final_state.vp_tracker else 0

    print("\n=== MATCH FINISHED ===")
    print(f"Total steps: {step}")
    print(f"Winner:      {final_state.winner}")
    print(f"Reason:      {final_state.end_reason}")
    print(f"Final VP:    {vp}")

    replay_observer.replay.meta["result"] = {
        "winner": final_state.winner,
        "reason": final_state.end_reason,
        "vp": vp,
        "steps": step,
    }

    # -------------------------------------------------
    # SAVE REPLAY
    # -------------------------------------------------
    replay_dir = Path("C:/repos/python/assault/assault_sim/session/replays")
    replay_dir.mkdir(parents=True, exist_ok=True)

    replay_path = replay_dir / (
        f"{sim_config.scenario_name}__"
        f"{rl_side}_RL_vs_{enemy_side}_HEURISTIC.json"
    )

    ReplayWriter.write(replay_observer.replay, replay_path)

    print(f"[OK] Replay saved to: {replay_path}")


if __name__ == "__main__":
    main()
