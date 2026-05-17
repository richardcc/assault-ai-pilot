from assault_model.actions.status import WaitAction
from assault_sim.rl.tactical_options import TacticalOption
import random


def collect_rollout(env, controller, steps):

    obs = env.reset()

    controller.policy.reset_hidden()

    # ✅ buffers finales
    obs_buf = []
    actions_buf = []
    attack_modes_buf = []
    logp_buf = []
    values_buf = []
    rewards_buf = []
    dones_buf = []

    # 🔥 NUEVO: buffer de secuencias
    sequence = []

    SEQ_LEN = 8

    step_count = 0

    turn_reward = 0.0
    turn_start_obs = None

    while step_count < steps:

        state = env.state
        active = state.active_unit if state else None

        if active is None:
            action = WaitAction("SYSTEM")

        else:

            # ---------------- RL SIDE ----------------
            if active.side == controller.rl_side:

                if turn_start_obs is None:
                    turn_start_obs = obs

                action = controller.choose_action(state, obs)

                last_option = controller.policy.last_option
                last_action = last_option.value
                last_attack_mode = controller.policy.last_attack_mode
                last_logp = controller.policy.last_log_prob.detach()
                last_value = controller.policy.last_value.item()

            # ---------------- ENEMY ----------------
            else:

                enemy_option = random.choice([
                    TacticalOption.ATTACK,
                    TacticalOption.ADVANCE,
                    TacticalOption.FLANK,
                    TacticalOption.HOLD,
                ])

                action = controller.executor.execute(state, enemy_option)

            if action is None:
                action = WaitAction(active.unit_id)

        # ---------------- STEP ----------------
        next_obs, reward, done, info = env.step(action)

        # acumular reward RL
        if active is not None and active.side == controller.rl_side:
            turn_reward += reward

        # detectar fin turno RL
        next_state = env.state
        next_active = next_state.active_unit if next_state else None

        rl_turn_finished = (
            active is not None
            and active.side == controller.rl_side
            and next_active is not None
            and next_active.side != controller.rl_side
        )

        # ---------------- STORE EN SECUENCIA ----------------
        if rl_turn_finished and turn_start_obs is not None:

            sequence.append({
                "obs": turn_start_obs,
                "action": last_action,
                "attack_mode": last_attack_mode if last_attack_mode is not None else 0,
                "logp": last_logp,
                "value": last_value,
                "reward": turn_reward,
                "done": done
            })

            # ✅ si tenemos secuencia suficiente → guardar
            if len(sequence) >= SEQ_LEN:

                chunk = sequence[:SEQ_LEN]

                obs_buf.extend([x["obs"] for x in chunk])
                actions_buf.extend([x["action"] for x in chunk])
                attack_modes_buf.extend([x["attack_mode"] for x in chunk])
                logp_buf.extend([x["logp"] for x in chunk])
                values_buf.extend([x["value"] for x in chunk])
                rewards_buf.extend([x["reward"] for x in chunk])
                dones_buf.extend([x["done"] for x in chunk])

                # sliding window
                sequence = sequence[1:]

            turn_reward = 0.0
            turn_start_obs = None

        # ---------------- avanzar ----------------
        obs = next_obs
        step_count += 1

        # ---------------- RESET ----------------
        if done:
            obs = env.reset()
            controller.policy.reset_hidden()

            sequence = []
            turn_reward = 0.0
            turn_start_obs = None

    # ---------------- seguridad ----------------
    if len(attack_modes_buf) < len(actions_buf):
        attack_modes_buf += [0] * (len(actions_buf) - len(attack_modes_buf))

    return {
        "obs": obs_buf,
        "actions": actions_buf,
        "attack_modes": attack_modes_buf,
        "logp": logp_buf,
        "values": values_buf,
        "rewards": rewards_buf,
        "dones": dones_buf,
    }
