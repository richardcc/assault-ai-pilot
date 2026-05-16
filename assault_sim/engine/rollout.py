from assault_model.actions.status import WaitAction
from assault_sim.rl.tactical_options import TacticalOption


def collect_rollout(env, controller, steps):

    obs = env.reset()

    # ✅ buffers locales (rápidos)
    obs_buf = []
    actions_buf = []
    logp_buf = []
    values_buf = []
    rewards_buf = []
    dones_buf = []

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

                # ✅ guardar datos PPO
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
            # fallback seguro
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

            if isinstance(action, WaitAction):
                reward -= 0.05

            obs_buf.append(last_obs)
            actions_buf.append(last_action)
            logp_buf.append(last_logp)
            values_buf.append(last_value)
            rewards_buf.append(reward)
            dones_buf.append(done)

        obs = next_obs
        step_count += 1

        # -------------------------------------------------
        # RESET EPISODIO
        # -------------------------------------------------
        if done:
            obs = env.reset()

    # ✅ construir dict al final (más eficiente)
    return {
        "obs": obs_buf,
        "actions": actions_buf,
        "logp": logp_buf,
        "values": values_buf,
        "rewards": rewards_buf,
        "dones": dones_buf,
    }


# ✅ compatibilidad
run_episode = collect_rollout
