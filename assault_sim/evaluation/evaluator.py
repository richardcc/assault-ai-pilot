from collections import defaultdict

from assault_sim.evaluation.metrics_tracker import MetricsTracker
from assault_sim.engine.match_runner import MatchRunner


class Evaluator:

    def __init__(
        self,
        env,
        rl_controller,
        enemy_controller,  # compatibilidad, no usado
        rl_side: str,
        max_steps: int = 300,
    ):
        self.env = env
        self.rl_controller = rl_controller
        self.enemy_controller = enemy_controller
        self.rl_side = rl_side
        self.max_steps = max_steps

    # -------------------------------------------------
    # RUN SINGLE EPISODE
    # -------------------------------------------------
    def run_episode(self):

        tracker = MetricsTracker(self.rl_side)

        # ✅ 🔥 SOLO conectar si existe el event_bus
        if self.env.sim.event_bus is not None:
            self.env.sim.event_bus.subscribe(tracker)

        # ✅ L2 / L3 tracking
        option_counts = defaultdict(int)
        formation_counts = defaultdict(int)
        strategy_option_map = defaultdict(lambda: defaultdict(int))

        # ✅ reset ANTES de crear runner
        obs = self.env.reset()
        runner = MatchRunner(self.env, controller=self.rl_controller)

        done = False
        steps = 0
        prev_state = self.env.sim.game_state
        while not done:

            step = runner.step(self.rl_controller, obs)
            info = step.get("info", {}) or {}
            obs = step["obs"]
            done = step["done"]

            side = step.get("side")

            state = self.env.sim.game_state

            # -------------------------------------------------
            # ✅ TRACK L2 / L3 (policy real)
            # -------------------------------------------------
            if side == self.rl_side:

                policy = self.rl_controller.hrl_controller.policy

                # ----- L2 -----
                option = policy.last_option
                if option is not None:
                    option_counts[option.name] += 1

                # ----- L3 -----
                formation = None
                hrl = self.rl_controller.hrl_controller

                if hasattr(hrl, "formation_engine"):
                    strat_obj = hrl.formation_engine.current_strategy
                    if strat_obj is not None:
                        formation = strat_obj.name
                        formation_counts[formation] += 1

                # ----- mapping L3 → L2 -----
                if option is not None and formation is not None:
                    strategy_option_map[formation][option.name] += 1

            # -------------------------------------------------
            # ✅ TRACK STATE (vida / daño recibido)
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

                print(
                    f"[EP {ep}] winner={result.get('winner')} "
                    f"vp={result.get('vp')} steps={result.get('steps')}"
                )

            except Exception as e:
                print(f"❌ ERROR in episode {ep}: {e}")

        return results