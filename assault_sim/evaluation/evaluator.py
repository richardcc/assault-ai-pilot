from collections import defaultdict
import numpy as np

from assault_sim.evaluation.metrics_tracker import MetricsTracker
from assault_sim.engine.match_runner import MatchRunner


class Evaluator:

    def __init__(
        self,
        env,
        rl_controller,
        enemy_controller,  # legacy (no usado)
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

        # ✅ tolerante a distintas implementaciones
        sim = getattr(self.env, "sim", None) or getattr(self.env, "sim_env", None)

        if sim is not None and getattr(sim, "event_bus", None) is not None:
            sim.event_bus.subscribe(tracker)

        # -------------------------------
        # POLICY TRACKING
        # -------------------------------
        option_counts = defaultdict(int)
        formation_counts = defaultdict(int)
        strategy_option_map = defaultdict(lambda: defaultdict(int))

        reward_trace = []

        obs = self.env.reset()

        # ✅ reset controller (LSTM, etc.)
        if hasattr(self.controller, "reset"):
            self.controller.reset()

        runner = MatchRunner(self.env, controller=self.controller)

        done = False
        steps = 0

        sim = getattr(self.env, "sim", None) or getattr(self.env, "sim_env", None)
        prev_state = sim.game_state if sim is not None else None

        # -------------------------------------------------
        # MAIN LOOP
        # -------------------------------------------------
        while not done:

            step = runner.step(self.controller, obs)

            info = step.get("info", {}) or {}
            obs = step["obs"]
            done = step["done"]
            side = step.get("side")

            sim = getattr(self.env, "sim", None) or getattr(self.env, "sim_env", None)
            state = sim.game_state if sim is not None else None

            reward_trace.append(step.get("reward", 0.0))

            # -------------------------------------------------
            # ✅ TRACK POLICY (L2 / L3)
            # -------------------------------------------------
            if side == self.rl_side:

                controller = self.controller

                # L2
                option = getattr(controller, "current_option", None)
                if option is not None:
                    option_counts[option.name] += 1

                # L3
                strategy = getattr(controller, "current_strategy", None)
                formation = None

                if strategy is not None:
                    formation = strategy.name
                    formation_counts[formation] += 1

                # mapping strategy → option
                if option is not None and formation is not None:
                    strategy_option_map[formation][option.name] += 1

            # -------------------------------------------------
            # ✅ TRACK METRICS (CRÍTICO)
            # -------------------------------------------------
            tracker.track_damage(info, state, prev_state)
            tracker.track_state(state)
            tracker.step()

            prev_state = state
            steps += 1

            # SAFETY
            if steps >= self.max_steps:
                done = True
                break

        # -------------------------------------------------
        # BUILD RESULT
        # -------------------------------------------------
        final_state = state if state is not None else None

        result = tracker.build_result(final_state)

        # ✅ métricas adicionales
        result["steps"] = steps
        result["avg_reward"] = float(np.mean(reward_trace)) if reward_trace else 0.0

        # ✅ POLICY INFO
        result["option_counts"] = dict(option_counts)
        result["formation_counts"] = dict(formation_counts)

        result["strategy_option_map"] = {
            k: dict(v) for k, v in strategy_option_map.items()
        }

        return result

    # -------------------------------------------------
    # MULTI EPISODE
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