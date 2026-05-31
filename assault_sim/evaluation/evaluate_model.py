import torch
from pathlib import Path
from multiprocessing import Pool, cpu_count, freeze_support

from tqdm import tqdm

from assault_sim.config.config_loader import load_sim_config
from assault_sim.sim_env import SimEnv
from assault_sim.training_env import TrainingEnv

from assault_sim.rl.policy_net import PolicyNet
from assault_sim.rl.tactical_options import TacticalOption
from assault_sim.rl.option_policy import OptionPolicy

from assault_sim.decision.decision_engine import DecisionEngine
from assault_sim.decision.decision_engine_controller import DecisionEngineController

from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic

from assault_sim.evaluation.results import ResultsAnalyzer
from assault_sim.evaluation.eval_dashboard import EvalDashboard
from assault_sim.evaluation.evaluator import Evaluator

from assault_sim.debug.debug_config import DebugConfig


# -------------------------------------------------
# CONFIG
# -------------------------------------------------
RL_SIDE = "US"
EPISODES = 500

CONFIG_PATH = Path("C:/repos/python/assault/assault_sim/config/sim_config.yaml")
ENV_CONFIG = Path("C:/repos/python/assault/assault_sim/config/env_config.json")
CHECKPOINT = Path("models/latest.pt")

NUM_WORKERS = min(6, cpu_count())


# -------------------------------------------------
# GLOBAL
# -------------------------------------------------
_policy = None


# -------------------------------------------------
# BUILD MODEL
# -------------------------------------------------
def get_policy(env):
    global _policy

    if _policy is not None:
        return _policy

    obs = env.reset()
    input_dim = obs.shape[0]

    policy = PolicyNet(
        input_dim=input_dim,
        num_options=len(TacticalOption),
    )

    checkpoint = torch.load(CHECKPOINT, map_location="cpu")
    policy.load_state_dict(checkpoint)
    policy.eval()

    _policy = policy
    return policy


# -------------------------------------------------
# BUILD ENV
# -------------------------------------------------
def build_env():

    sim_config = load_sim_config(CONFIG_PATH)
    sim_config.scenario_name = "phase01_seq001_initial_contact"

    sim_env = SimEnv(
        sim_config,
        controller=None,
        debug_config=DebugConfig(enabled=False),
    )

    env = TrainingEnv(
        sim_env,
        env_config_path=ENV_CONFIG,
        rl_side=RL_SIDE,
    )

    return env, sim_env


# -------------------------------------------------
# BUILD CONTROLLER
# -------------------------------------------------
def build_controller(policy, sim_env):

    decision_engine = DecisionEngine()
    option_policy = OptionPolicy(policy)
    heuristic = TacticalPathHeuristic()

    controller = DecisionEngineController(
        rl_side=RL_SIDE,
        decision_engine=decision_engine,
        option_policy=option_policy,
        heuristic=heuristic,
        sim_env=sim_env,
    )

    controller.training_mode = False
    return controller


# -------------------------------------------------
# RUN 1 EPISODE (SAFE VERSION)
# -------------------------------------------------
def run_episode(_):

    try:
        env, sim_env = build_env()
        policy = get_policy(env)
        controller = build_controller(policy, sim_env)

        evaluator = Evaluator(
            env=env,
            rl_controller=controller,
            enemy_controller=None,
            rl_side=RL_SIDE,
        )

        with torch.no_grad():
            results = evaluator.evaluate(1)

        if not results:
            return None, {}, {}

        result = results[0]

        combat = result.get("combat", {})
        advanced = result.get("advanced", {})

        return result, combat, advanced

    except Exception:
        # multiprocessing safe fallback
        return None, {}, {}


# -------------------------------------------------
# MAIN
# -------------------------------------------------
def main():

    print(f">>> Parallel evaluation ({EPISODES} episodes)")
    print(f">>> Workers: {NUM_WORKERS}")

    results = []

    # -------------------------------------------------
    # AGGREGATORS
    # -------------------------------------------------
    agg = {
        # combat
        "trade_sum": 0.0,
        "trade_count": 0,
        "bad_attacks": 0,
        "total_attacks": 0,
        "damage_sum": 0.0,
        "damage_taken_sum": 0.0,

        # advanced
        "good_trades": 0,
        "bad_trades": 0,
        "zero_damage_attacks": 0,
        "turns_in_range": 0,
        "attacks_in_range": 0,
    }

    # -------------------------------------------------
    # PARALLEL LOOP
    # -------------------------------------------------
    with Pool(NUM_WORKERS) as p:

        for result, combat, advanced in tqdm(
            p.imap_unordered(run_episode, range(EPISODES), chunksize=5),
            total=EPISODES,
            desc="Evaluating",
        ):

            # ✅ skip broken episodes
            if result is None:
                continue

            results.append(result)

            # --------------------------
            # COMBAT
            # --------------------------
            trade_mean = combat.get("trade_mean", 0.0)
            bad_rate = combat.get("bad_attack_rate", 0.0)
            total_attacks = combat.get("total_attacks", 0)

            damage = result["side"]["RL"].get("damage", 0)
            enemy_damage = result["side"]["ENEMY"].get("damage", 0)

            agg["trade_sum"] += trade_mean * total_attacks
            agg["trade_count"] += total_attacks

            agg["bad_attacks"] += bad_rate * total_attacks
            agg["total_attacks"] += total_attacks

            agg["damage_sum"] += damage
            agg["damage_taken_sum"] += enemy_damage

            # --------------------------
            # ADVANCED
            # --------------------------
            agg["good_trades"] += advanced.get("good_trades", 0)
            agg["bad_trades"] += advanced.get("bad_trades", 0)
            agg["zero_damage_attacks"] += advanced.get("zero_damage_attacks", 0)
            agg["turns_in_range"] += advanced.get("turns_in_range", 0)
            agg["attacks_in_range"] += advanced.get("attacks_in_range", 0)

    print(">>> Episodes finished ✅")

    # -------------------------------------------------
    # FINAL METRICS
    # -------------------------------------------------
    trade_mean = agg["trade_sum"] / max(1, agg["trade_count"])
    bad_attack_rate = agg["bad_attacks"] / max(1, agg["total_attacks"])
    damage_ratio = agg["damage_sum"] / max(1, agg["damage_taken_sum"])

    print("\n=== COMBAT INTELLIGENCE ===")
    print(f"trade_mean:      {trade_mean:.3f}")
    print(f"bad_attack_rate: {bad_attack_rate:.3f}")
    print(f"damage_ratio:    {damage_ratio:.3f}")

    # -------------------------------------------------
    # ✅ ADVANCED METRICS (FIXED)
    # -------------------------------------------------
    print("\n=== ADVANCED METRICS ===")

    total_attacks = max(1, agg["good_trades"] + agg["bad_trades"])
    range_total = max(1, agg["turns_in_range"])

    print(f"good_trade_rate:  {agg['good_trades'] / total_attacks:.3f}")
    print(f"bad_trade_rate:   {agg['bad_trades'] / total_attacks:.3f}")
    print(f"selectivity:      {agg['attacks_in_range'] / range_total:.3f}")
    print(f"zero_dmg_rate:    {agg['zero_damage_attacks'] / total_attacks:.3f}")

    # -------------------------------------------------
    # DASHBOARD + REPORT
    # -------------------------------------------------
    dashboard = EvalDashboard()
    for r in results:
        dashboard.add_episode(r)

    analyzer = ResultsAnalyzer(results, RL_SIDE)
    analyzer.print_report()

    dashboard.save_csv("metrics.csv")
    dashboard.plot_all()

    print("\n>>> EVALUATION FINISHED ✅")


# -------------------------------------------------
# ENTRY POINT
# -------------------------------------------------
if __name__ == "__main__":
    freeze_support()
    main()