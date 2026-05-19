from assault_sim.engine.match_runner import MatchRunner


def collect_rollout(env, controller, max_steps, seq_len=8):

    runner = MatchRunner(env)

    obs = runner.reset()
    controller.hrl_controller.policy.reset_hidden()

    obs_buf, actions_buf = [], []
    attack_modes_buf, logp_buf = [], []
    values_buf, rewards_buf, dones_buf = [], [], []

    sequence = []

    turn_start_obs = None
    turn_reward = 0.0

    step_count = 0

    last_action = None
    last_attack_mode = 0
    last_logp = None
    last_value = None

    # ✅ DEBUG LIMIT
    DEBUG_STEPS = 60

    while step_count < max_steps or len(sequence) == 0:

        policy = controller.hrl_controller.policy

        step = runner.step(controller, obs)

        next_obs = step["obs"]
        reward = step["reward"]
        done = step["done"]
        side = step["side"]
        unit = step.get("unit")
        action_obj = step.get("action")


        # -------------------------------------------------
        # ✅ INICIO TURNO RL
        # -------------------------------------------------
        if side == controller.rl_side:

            if turn_start_obs is None:
                turn_start_obs = obs

            last_option = policy.last_option


            if last_option is not None:
                last_action = last_option.value
                last_attack_mode = (
                    policy.last_attack_mode
                    if policy.last_attack_mode is not None else 0
                )

            if policy.last_log_prob is not None:
                last_logp = policy.last_log_prob.detach()

            if policy.last_value is not None:
                last_value = policy.last_value.item()

            turn_reward += reward

        # -------------------------------------------------
        # ✅ FIN TURNO RL
        # -------------------------------------------------
        if step.get("is_rl_turn_end", False) and turn_start_obs is not None:

            if last_action is None:
                last_action = 0
            if last_logp is None:
                last_logp = 0.0
            if last_value is None:
                last_value = 0.0

            sequence.append({
                "obs": turn_start_obs,
                "action": last_action,
                "attack_mode": last_attack_mode,
                "logp": last_logp,
                "value": last_value,
                "reward": turn_reward,
                "done": done,
            })

            turn_start_obs = None
            turn_reward = 0.0

            if len(sequence) >= seq_len:

                chunk = sequence[:seq_len]
                sequence = sequence[1:]

                obs_buf.extend([x["obs"] for x in chunk])
                actions_buf.extend([x["action"] for x in chunk])
                attack_modes_buf.extend([x["attack_mode"] for x in chunk])
                logp_buf.extend([x["logp"] for x in chunk])
                values_buf.extend([x["value"] for x in chunk])
                rewards_buf.extend([x["reward"] for x in chunk])
                dones_buf.extend([x["done"] for x in chunk])

        # -------------------------------------------------
        # AVANCE
        # -------------------------------------------------
        obs = next_obs
        step_count += 1

        # -------------------------------------------------
        # RESET EPISODIO
        # -------------------------------------------------
        if done:
            obs = runner.reset()
            controller.hrl_controller.policy.reset_hidden()

            turn_start_obs = None
            turn_reward = 0.0

    # -------------------------------------------------
    # FLUSH FINAL
    # -------------------------------------------------
    if len(sequence) > 0:
        for x in sequence:
            obs_buf.append(x["obs"])
            actions_buf.append(x["action"])
            attack_modes_buf.append(x["attack_mode"])
            logp_buf.append(x["logp"])
            values_buf.append(x["value"])
            rewards_buf.append(x["reward"])
            dones_buf.append(x["done"])

    return {
        "obs": obs_buf,
        "actions": actions_buf,
        "attack_modes": attack_modes_buf,
        "logp": logp_buf,
        "values": values_buf,
        "rewards": rewards_buf,
        "dones": dones_buf,
    }