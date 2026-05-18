from pathlib import Path
import argparse
import torch

from assault_sim.config.config_loader import load_sim_config
from assault_sim.sim_env import SimEnv
from assault_sim.training_env import TrainingEnv

from assault_sim.debug.console_observer import ConsoleObserver
from assault_sim.debug.debug_config import DebugConfig

# ✅ HRL stack
from assault_sim.rl.option_policy import OptionPolicy
from assault_sim.decision.hrl_controller import HRLController
from assault_sim.decision.option_executor import OptionExecutor
from assault_sim.rl.tactical_options import TacticalOption
from assault_sim.rl.policy_net import PolicyNet

# ✅ heuristic
from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic

# ✅ IMPORTANTE
from assault_model.actions.status import WaitAction


RL_SIDE = "US"
CHECKPOINT = Path("models/latest.pt")  # ✅ ALINEADO con train_ppo
import json
from pathlib import Path


class SimpleReplayRecorder:

    def __init__(self, path: Path):
        self.events = []
        self.path = path

    def on_event(self, event):
        self.events.append(event)

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.events, f, indent=2)

# -----------------------------------------------------
# CLI
# -----------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(description="Assault runner")

    parser.add_argument(
        "--config",
        type=Path,
        default=Path("assault_sim/config/sim_config.yaml"),
    )
    parser.add_argument("--scenario", type=str)
    parser.add_argument("--debug", action="store_true")

    return parser.parse_args()


# -----------------------------------------------------
# ✅ LOAD MODEL (NUEVO FORMATO CORRECTO)
# -----------------------------------------------------
def load_model(config_path, scenario):

    print(">>> Loading model")

    # ✅ crear env SOLO para input_dim
    sim_config = load_sim_config(config_path)
    sim_config.scenario_name = scenario

    sim_env = SimEnv(sim_config)

    env = TrainingEnv(
        sim_env,
        env_config_path=Path("assault_sim/config/env_config.json"),
        rl_side=RL_SIDE,
    )

    obs = env.reset()
    input_dim = obs.shape[0]

    # ✅ modelo nuevo
    policy_net = PolicyNet(
        input_dim=input_dim,
        num_options=len(TacticalOption)
    )

    # ✅ cargar pesos (state_dict directo)
    checkpoint = torch.load(CHECKPOINT, map_location="cpu")
    policy_net.load_state_dict(checkpoint)

    policy_net.eval()

    return policy_net


# -----------------------------------------------------
# BUILD CONTROLLERS
# -----------------------------------------------------
def build_controllers(policy_net):

    heuristic = TacticalPathHeuristic()

    # ✅ IMPORTANTE: envolver en OptionPolicy
    option_policy = OptionPolicy(policy_net)
    executor_rl = OptionExecutor(heuristic)

    rl_controller = HRLController(
        option_policy=option_policy,
        option_executor=executor_rl,
        rl_side=RL_SIDE,
    )

    # ✅ enemy baseline
    executor_enemy = OptionExecutor(heuristic)

    class EnemyController:
        def choose_action(self, state, obs):
            return executor_enemy.execute(
                state,
                TacticalOption.ATTACK
            )

    return rl_controller, EnemyController()


# -----------------------------------------------------
# MAIN
# -----------------------------------------------------
def main():

    args = parse_args()

    sim_config = load_sim_config(args.config)

    if args.scenario:
        sim_config.scenario_name = args.scenario
    else:
        sim_config.scenario_name = "phase01_seq001_initial_contact"

    debug_cfg = DebugConfig(enabled=args.debug)

    sim_env = SimEnv(
        sim_config,
        debug_config=debug_cfg,
        controller=None,
    )

    env = TrainingEnv(
        sim_env,
        env_config_path=Path("assault_sim/config/env_config.json"),
        rl_side=RL_SIDE,
    )

    observer = ConsoleObserver(rl_side=RL_SIDE)
    replay_path = Path(
        f"assault_sim/session/replays/{sim_config.scenario_name}__RL_run.json"
    )
    recorder = SimpleReplayRecorder(replay_path)

    if sim_env.event_bus:
        sim_env.event_bus.subscribe(observer)
        sim_env.event_bus.subscribe(recorder.on_event)

    # ✅ ✅ CLAVE: cargar modelo correctamente
    policy_net = load_model(args.config, sim_config.scenario_name)

    rl_controller, enemy_controller = build_controllers(policy_net)

    obs = env.reset()
    done = False
    step_count = 0

    while not done:

        state = env.state
        active = state.active_unit if state else None

        # -----------------------------------------
        # SELECT ACTION
        # -----------------------------------------
        if active is None:
            action = WaitAction("SYSTEM")

        elif active.side == RL_SIDE:

            action = rl_controller.choose_action(state, obs)

            if action is None:
                action = WaitAction(active.unit_id)

        else:
            action = enemy_controller.choose_action(state, obs)

        # -----------------------------------------
        # STEP
        # -----------------------------------------
        obs, reward, done, info = env.step(action)

        step_count += 1

        if step_count >= 500:
            print("⚠️ Forced stop")
            break

    state = env.state

    print("\n=== SIMULATION FINISHED ===")
    print(f"Winner: {state.winner}")
    print(f"Reason: {state.end_reason}")
    print(f"Turns:  {state.turn}")
    recorder.save()
    print(f"✅ Replay saved to: {recorder.path}")

    if state.vp_tracker:
        print(f"Final VP: {state.vp_tracker.total_points}")


# -----------------------------------------------------
if __name__ == "__main__":
    main()
