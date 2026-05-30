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
        self.controller = rl_controller  # ✅ único controller
        self.rl_side = rl_side
        self.max_steps = max_steps

    # -------------------------------------------------
    # RUN SINGLE EPISODE
    # -------------------------------------------------
    def run_episode(self):

        tracker = MetricsTracker(self.rl_side)

        if self.env.sim.event_bus is not None:
            self.env.sim.event_bus.subscribe(tracker)

        # ✅ tracking
        option_counts = defaultdict(int)
        formation_counts = defaultdict(int)
        strategy_option_map = defaultdict(lambda: defaultdict(int))

        reward_trace = []

        obs = self.env.reset()

        # ✅ CRÍTICO: reset controller (LSTM + strategy)
        if hasattr(self.controller, "reset"):
            self.controller.reset()

        runner = MatchRunner(self.env, controller=self.controller)

        done = False
        steps = 0
        prev_state = self.env.sim.game_state

        while not done:

            step = runner.step(self.controller, obs)

            info = step.get("info", {}) or {}
            obs = step["obs"]
            done = step["done"]
            side = step.get("side")

            state = self.env.sim.game_state

            reward_trace.append(step["reward"])

            # -------------------------------------------------
            # ✅ TRACK POLICY
            # -------------------------------------------------
            if side == self.rl_side:

                controller = self.controller

                # ✅ OPTION (L2)
                option = getattr(controller, "current_option", None)
                if option is not None:
                    option_counts[option.name] += 1

                # ✅ STRATEGY (L3) ✅ CAMBIO CLAVE
                strategy = getattr(controller, "current_strategy", None)
                formation = None

                if strategy is not None:
                    formation = strategy.name
                    formation_counts[formation] += 1

                # ✅ mapping L3 → L2
                if option is not None and formation is not None:
                    strategy_option_map[formation][option.name] += 1

            # -------------------------------------------------
            # ✅ TRACK STATE
            # -------------------------------------------------
            tracker.track_damage(info, state, prev_state)
            tracker.track_state(state)
            tracker.step()

            prev_state = state
            steps += 1

            # -------------------------------------------------
            # SAFETY LIMIT
            # -------------------------------------------------
            if steps >= self.max_steps:
                done = True
                break

        # -------------------------------------------------
        # BUILD RESULT
        # -------------------------------------------------
        result = tracker.build_result(self.env.sim.game_state)

        result["steps"] = steps
        result["avg_reward"] = float(np.mean(reward_trace)) if reward_trace else 0.0

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

                #print(
                 #   f"[EP {ep}] "
                  #  f"winner={result.get('winner')} "
                   # f"vp={result.get('vp')} "
                    #f"steps={result.get('steps')} "
                    #f"avg_reward={result.get('avg_reward'):.3f}"
               # )

            except Exception as e:
                print(f"❌ ERROR in episode {ep}: {e}")

        return results