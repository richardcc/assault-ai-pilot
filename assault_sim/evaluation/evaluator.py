from assault_sim.evaluation.metrics_tracker import MetricsTracker
from assault_model.actions.status import WaitAction
from collections import defaultdict


class Evaluator:

    def __init__(
        self,
        env,
        rl_controller,
        enemy_controller,
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

        # -----------------------------
        # L2 usage
        # -----------------------------
        option_counts = defaultdict(int)

        # -----------------------------
        # L3 usage
        # -----------------------------
        formation_counts = defaultdict(int)

        # -----------------------------
        # L3 -> L2 mapping
        # -----------------------------
        strategy_option_map = defaultdict(lambda: defaultdict(int))

        obs = self.env.reset()
        done = False

        prev_state = self.env.state

        while not done:

            state = self.env.state
            active = state.active_unit if state else None

            # -----------------------------------------
            # SELECT ACTION
            # -----------------------------------------
            if active is None:
                action = WaitAction("SYSTEM")

            elif active.side == self.rl_side:

                action = self.rl_controller.choose_action(state, obs)

                # -----------------------------
                # L2 OPTION
                # -----------------------------
                option = getattr(self.rl_controller, "current_option", None)

                # -----------------------------
                # L3 FORMATION
                # -----------------------------
                formation = None
                if hasattr(self.rl_controller, "formation_engine"):
                    formation_obj = self.rl_controller.formation_engine.current_strategy
                    if formation_obj is not None:
                        formation = formation_obj.name
                        formation_counts[formation] += 1

                # -----------------------------
                # TRACK L2
                # -----------------------------
                if option is not None:
                    option_counts[option.name] += 1

                    # -----------------------------
                    # TRACK L3 -> L2 RELATION
                    # -----------------------------
                    if formation is not None:
                        strategy_option_map[formation][option.name] += 1

            else:
                action = self.enemy_controller.choose_action(state, obs)

            # -----------------------------------------
            # SAFETY: never None
            # -----------------------------------------
            if action is None and active is not None:
                action = WaitAction(active.unit_id)

            # -----------------------------------------
            # TRACK BEFORE STEP
            # -----------------------------------------
            current_state = state
            tracker.track_action(current_state, action)

            # -----------------------------------------
            # STEP
            # -----------------------------------------
            obs, reward, done, info = self.env.step(action)

            next_state = self.env.state

            # -----------------------------------------
            # TRACK AFTER STEP
            # -----------------------------------------
            if prev_state is not None and next_state is not None:
                tracker.track_damage(info, next_state, prev_state)
                tracker.track_kills(next_state, prev_state)

            tracker.track_state(next_state)
            tracker.step()

            prev_state = next_state

            # -----------------------------------------
            # SAFETY LIMIT
            # -----------------------------------------
            if tracker.steps >= self.max_steps:
                done = True
                break

        # -----------------------------------------
        # BUILD RESULT
        # -----------------------------------------
        result = tracker.build_result(self.env.state)

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
            result = self.run_episode()
            results.append(result)

            winner = result["winner"]
            vp = result["vp"]
            steps = result["steps"]

            print(f"[EP {ep}] winner={winner} vp={vp} steps={steps}")

        return results
