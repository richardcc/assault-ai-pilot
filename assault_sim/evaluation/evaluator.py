from collections import defaultdict
import numpy as np

from assault_sim.evaluation.metrics_tracker import MetricsTracker
from assault_sim.engine.match_runner import MatchRunner
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
        advanced_metrics = AdvancedMetrics()

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

        # ✅ CRÍTICO → LOG REAL DE EVENTOS
        events_log = []

        obs = self.env.reset()

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

            if state is None:
                break

            final_state = state

            reward_trace.append(step.get("reward", 0.0))

            # -------------------------------------------------
            # ✅ EVENT CAPTURE (FIX REAL ROBUSTO)
            # -------------------------------------------------
            for key in ["attack_events", "events", "combat_events", "attacks"]:

                if key not in info:
                    continue

                for e in info[key]:

                    if not isinstance(e, dict):
                        continue

                    attack_type = (
                        e.get("attack_type")
                        or e.get("type")
                        or e.get("action")
                    )

                    if attack_type is None:
                        continue

                    events_log.append({
                        "type": "attack",
                        "attack_type": str(attack_type),
                        "damage": e.get("damage", 0),
                        "attacker": e.get("attacker"),
                        "target": e.get("target"),
                    })
                
            # end for key in ...

            # -------------------------------------------------
            # FALLBACK: synthesize an event from info fields
            # if no explicit event lists are provided by the env
            # -------------------------------------------------
            action_type = info.get("action_type")
            rl_dmg = info.get("rl_damage", 0)
            enemy_dmg = info.get("enemy_damage", 0)
            rl_atk = info.get("rl_attacks", 0)
            enemy_atk = info.get("enemy_attacks", 0)

            is_attack_action = action_type in ("direct", "indirect", "assault")

            if is_attack_action and (rl_dmg or enemy_dmg or rl_atk or enemy_atk):
                # determine attacker side for this step
                atk_side = side

                atk_damage = 0
                if atk_side == self.rl_side:
                    atk_damage = rl_dmg
                else:
                    atk_damage = enemy_dmg

                # normalize attack type
                atk_type_norm = None
                if action_type == "indirect":
                    atk_type_norm = "INDIRECT"
                elif action_type in ("direct", "assault"):
                    atk_type_norm = "DIRECT"
                else:
                    atk_type_norm = str(action_type).upper() if action_type else "OTHER"

                events_log.append({
                    "type": "attack",
                    "attack_type": atk_type_norm,
                    "damage": atk_damage,
                    "attacker": info.get("unit_id"),
                    "target": info.get("target_id") or info.get("target"),
                })

            # -------------------------------------------------
            # POLICY TRACKING
            # -------------------------------------------------
            if side == self.rl_side:

                option = getattr(self.controller, "current_option", None)
                if option is not None:
                    option_counts[option.name] += 1

                strategy = getattr(self.controller, "current_strategy", None)

                if strategy is not None:
                    formation = strategy.name
                    formation_counts[formation] += 1

                    if option is not None:
                        strategy_option_map[formation][option.name] += 1

            # -------------------------------------------------
            # DISTANCE
            # -------------------------------------------------
            pre_dist = None

            if hasattr(state, "units"):

                rl_units = [u for u in state.units if u.side == self.rl_side and u.alive]
                enemy_units = [u for u in state.units if u.side != self.rl_side and u.alive]

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
            # ADVANCED METRICS
            # -------------------------------------------------
            advanced_metrics.update(info, pre_dist)

            prev_state = state
            steps += 1

            if steps >= self.max_steps:
                break

        # -------------------------------------------------
        # BUILD RESULT
        # -------------------------------------------------
        result = tracker.build_result(final_state)

        result["steps"] = steps
        result["episode_length"] = steps
        result["avg_reward"] = float(np.mean(reward_trace)) if reward_trace else 0.0

        # -------------------------------------------------
        # POLICY TRACKING
        # -------------------------------------------------
        result["option_counts"] = dict(option_counts)
        result["formation_counts"] = dict(formation_counts)

        result["strategy_option_map"] = {
            strat: dict(opts) for strat, opts in strategy_option_map.items()
        }

        # -------------------------------------------------
        # ✅ GUARDAR EVENTOS (CLAVE)
        # -------------------------------------------------
        result["events"] = events_log

        # -------------------------------------------------
        # ADVANCED METRICS
        # -------------------------------------------------
        result["advanced"] = advanced_metrics.to_dict()

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