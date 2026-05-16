from assault_model.actions.status import WaitAction
from assault_sim.rl.tactical_options import TacticalOption


def collect_rollout(env, controller, steps):

    obs = env.reset()

    # ✅ buffers
    obs_buf = []
    actions_buf = []
    attack_modes_buf = []
    logp_buf = []
    values_buf = []
    rewards_buf = []
    dones_buf = []

    step_count = 0

    while step_count < steps:

        state = env.state
        active = state.active_unit if state else None

        # -------------------------------------------------
        # NO ACTIVE
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

                # ✅ PPO data
                last_obs = obs
                last_option = controller.policy.last_option
                last_action = last_option.value
                last_attack_mode = controller.policy.last_attack_mode
                last_logp = controller.policy.last_log_prob.detach()
                last_value = controller.policy.last_value.item()

                store = True

            # -------------------------------------------------
            # ENEMY SIDE (heuristic)
            # -------------------------------------------------
            else:
                action = controller.executor.execute(
                    state,
                    TacticalOption.ATTACK
                )
                store = False

            # -------------------------------------------------
            # SAFETY
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

            obs_buf.append(last_obs)
            actions_buf.append(last_action)

            attack_modes_buf.append(
                last_attack_mode if last_attack_mode is not None else 0
            )

            logp_buf.append(last_logp)
            values_buf.append(last_value)
            rewards_buf.append(reward)
            dones_buf.append(done)

        obs = next_obs
        step_count += 1

        # -------------------------------------------------
        # RESET
        # -------------------------------------------------
        if done:
            obs = env.reset()

    # -------------------------------------------------
    # ✅ SEGURIDAD FINAL
    # -------------------------------------------------
    if len(attack_modes_buf) != len(actions_buf):
        attack_modes_buf = [0] * len(actions_buf)

    return {
        "obs": obs_buf,
        "actions": actions_buf,
        "attack_modes": attack_modes_buf,
        "logp": logp_buf,
        "values": values_buf,
        "rewards": rewards_buf,
        "dones": dones_buf,
    }


# ✅ compatibilidad
run_episode = collect_rollout