from assault_model.actions.status import WaitAction
from assault_sim.rl.tactical_options import TacticalOption


def collect_rollout(env, controller, steps):

    obs = env.reset()

    trajectory = {
        "obs": [],
        "actions": [],
        "logp": [],
        "values": [],
        "rewards": [],
        "dones": [],
    }

    step_count = 0

    while step_count < steps:

        state = env.state
        active = state.active_unit if state else None

        # -------------------------------------------------
        # NO ACTIVE → avanzar turno
        # -------------------------------------------------
        if active is None:
            action = WaitAction("SYSTEM")
            store = False

        else:

            # -------------------------------------------------
            # RL SIDE
            # -------------------------------------------------
            if active.side == controller.rl_side:

                action = controller.choose_action(state, obs)

                # ✅ datos PPO
                last_obs = obs
                last_action = controller.policy.last_option.value
                last_logp = controller.policy.last_log_prob.detach()
                last_value = controller.policy.last_value.item()

                store = True

            # -------------------------------------------------
            # ENEMY SIDE
            # -------------------------------------------------
            else:

                action = controller.executor.execute(
                    state,
                    TacticalOption.ATTACK
                )

                store = False

            # -------------------------------------------------
            # NUNCA permitir None
            # -------------------------------------------------
            if action is None:
                action = WaitAction(active.unit_id)

        # -------------------------------------------------
        # STEP
        # -------------------------------------------------
        next_obs, reward, done, info = env.step(action)

        # -------------------------------------------------
        # STORE SOLO RL
        # -------------------------------------------------
        if store:

            # penalizar WAIT
            if isinstance(action, WaitAction):
                reward -= 0.05

            trajectory["obs"].append(last_obs)
            trajectory["actions"].append(last_action)
            trajectory["logp"].append(last_logp)
            trajectory["values"].append(last_value)
            trajectory["rewards"].append(reward)
            trajectory["dones"].append(done)

        obs = next_obs
        step_count += 1

        # -------------------------------------------------
        # RESET EPISODIO
        # -------------------------------------------------
        if done:
            obs = env.reset()

    return trajectory


# ✅ compatibilidad opcional
run_episode = collect_rollout