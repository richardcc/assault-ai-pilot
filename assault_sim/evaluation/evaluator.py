from collections import defaultdict
import numpy as np

from assault_sim.evaluation.metrics_tracker import MetricsTracker
from assault_sim.engine.match_runner import MatchRunner

# ✅ advanced metrics (correct import)
from assault_sim.evaluation.advanced_metrics import AdvancedMetrics


class Evaluator:

    def __init__(
        self,
        env,
        rl_controller,
        enemy_controller,  # legacy (not used)
        rl_side: str,
        max_steps: int = 300,
    ):
        self.env = env
        self.controller = rl_controller
        self.rl_side = rl_side
        self.max_steps = max_steps

    # -------------------------------------------------
    # RUN SINGLE EPISODE
    # -------------------------------------------------
    def run_episode(self):

        tracker = MetricsTracker(self.rl_side)
        advanced_metrics = AdvancedMetrics()  # ✅ NEW

        # -------------------------------------------------
        # EVENT BUS
        # -------------------------------------------------
        sim = getattr(self.env, "sim", None) or getattr(self.env, "sim_env", None)

        if sim is not None and getattr(sim, "event_bus", None) is not None:
            sim.event_bus.subscribe(tracker)

        # -------------------------------------------------
        # POLICY TRACKING
        # -------------------------------------------------
        option_counts = defaultdict(int)
        formation_counts = defaultdict(int)
        strategy_option_map = defaultdict(lambda: defaultdict(int))

        reward_trace = []

        obs = self.env.reset()

        # ✅ reset controller (important)
        if hasattr(self.controller, "reset"):
            self.controller.reset()

        runner = MatchRunner(self.env, controller=self.controller)

        done = False
        steps = 0

        prev_state = sim.game_state if sim is not None else None
        final_state = prev_state

        # -------------------------------------------------
        # MAIN LOOP
        # -------------------------------------------------
        while not done:

            step = runner.step(self.controller, obs)

            if not step:
                break

            info = step.get("info", {}) or {}
            obs = step.get("obs")
            done = step.get("done", False)
            side = step.get("side")

            sim = getattr(self.env, "sim", None) or getattr(self.env, "sim_env", None)
            state = sim.game_state if sim is not None else None

            if state is not None:
                final_state = state

            reward_trace.append(step.get("reward", 0.0))

            # -------------------------------------------------
            # POLICY TRACKING (L2 / L3)
            # -------------------------------------------------
            if side == self.rl_side:

                controller = self.controller

                option = getattr(controller, "current_option", None)
                if option is not None:
                    option_counts[option.name] += 1

                strategy = getattr(controller, "current_strategy", None)
                formation = None

                if strategy is not None:
                    formation = strategy.name
                    formation_counts[formation] += 1

                if option is not None and formation is not None:
                    strategy_option_map[formation][option.name] += 1

            # -------------------------------------------------
            # DISTANCE (for advanced metrics)
            # -------------------------------------------------
            pre_dist = None

            if state is not None and hasattr(state, "units"):

                rl_units = [
                    u for u in state.units
                    if u.side == self.rl_side and u.alive
                ]

                enemy_units = [
                    u for u in state.units
                    if u.side != self.rl_side and u.alive
                ]

                dists = []

                for u in rl_units:
                    for e in enemy_units:
                        if u.position and e.position:
                            dq = abs(u.position.q - e.position.q)
                            dr = abs(u.position.r - e.position.r)
                            dists.append(dq + dr)


                if dists:
                    pre_dist = min(dists)

            # -------------------------------------------------
            # CORE METRICS
            # -------------------------------------------------
            tracker.track_damage(info, state, prev_state)
            tracker.track_state(state)
            tracker.step()

            # -------------------------------------------------
            # ✅ ADVANCED METRICS
            # -------------------------------------------------
            advanced_metrics.update(info, pre_dist)

            prev_state = state
            steps += 1

            if steps >= self.max_steps:
                done = True
                break

        # -------------------------------------------------
        # BUILD RESULT
        # -------------------------------------------------
        result = tracker.build_result(final_state)

        result["steps"] = steps
        result["avg_reward"] = float(np.mean(reward_trace)) if reward_trace else 0.0

        # policy tracking
        result["option_counts"] = dict(option_counts)
        result["formation_counts"] = dict(formation_counts)

        result["strategy_option_map"] = {
            strat: dict(opts) for strat, opts in strategy_option_map.items()
        }

        # ✅ attach advanced metrics
        result["advanced"] = advanced_metrics.to_dict()

        return result

    # -------------------------------------------------
    # MULTI EPISODE (FIX CRÍTICO)
    # -------------------------------------------------
    def evaluate(self, episodes: int):

        results = []

        for ep in range(episodes):

            try:
                result = self.run_episode()
                results.append(result)

            except Exception as e:
                print(f"❌ ERROR in episode {ep}: {e}")

        return results