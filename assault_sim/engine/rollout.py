from assault_model.actions.status import WaitAction
from assault_sim.rl.tactical_options import TacticalOption
from assault_sim.engine.activation_manager import ActivationManager

import random


def collect_rollout(env, controller, steps):

    obs = env.reset()
    controller.policy.reset_hidden()

    activation_manager = ActivationManager(env.sim.game_state)

    # buffers
    obs_buf = []
    actions_buf = []
    attack_modes_buf = []
    logp_buf = []
    values_buf = []
    rewards_buf = []
    dones_buf = []

    sequence = []
    SEQ_LEN = 8

    step_count = 0
    turn_reward = 0.0
    turn_start_obs = None

    while step_count < steps:

        state = env.sim.game_state

        # ✅ NUEVO: scheduler
        side, unit = None, None

        for _ in range(len(activation_manager.sides) * 2):
            side, unit = activation_manager.next_activation()
            if unit is not None:
                break

        if unit is None:
            action = WaitAction("SYSTEM")
            next_obs, reward, done, _ = env.step(action)
            obs = next_obs
            step_count += 1
            continue

        # ---------------- RL SIDE ----------------
        if side == controller.rl_side:

            if turn_start_obs is None:
                turn_start_obs = obs

            action = controller.choose_action(state, unit, obs)

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

            action = controller.executor.execute(state, unit, enemy_option)

        # ✅ safety
        if action is None:
            action = WaitAction(unit.unit_id)

        # ---------------- STEP ----------------
        next_obs, reward, done, info = env.step(action)

        # ✅ CONEXIÓN CRÍTICA (igual que runner)
        activation_manager.state = env.sim.game_state
        activation_manager.blocked_units = env.sim.runtime.activated_units.copy()

        # acumular reward
        if side == controller.rl_side:
            turn_reward += reward

        # detectar cambio de turno RL
        next_state = env.sim.game_state

        # ✅ ya no existe active_unit → detectamos por scheduler
        next_side, _ = activation_manager.next_activation()

        rl_turn_finished = (
            side == controller.rl_side
            and next_side != controller.rl_side
        )

        # ---------------- STORE ----------------
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

            if len(sequence) >= SEQ_LEN:

                chunk = sequence[:SEQ_LEN]

                obs_buf.extend([x["obs"] for x in chunk])
                actions_buf.extend([x["action"] for x in chunk])
                attack_modes_buf.extend([x["attack_mode"] for x in chunk])
                logp_buf.extend([x["logp"] for x in chunk])
                values_buf.extend([x["value"] for x in chunk])
                rewards_buf.extend([x["reward"] for x in chunk])
                dones_buf.extend([x["done"] for x in chunk])

                sequence = sequence[1:]

            turn_reward = 0.0
            turn_start_obs = None

        obs = next_obs
        step_count += 1

        if done:
            obs = env.reset()
            controller.policy.reset_hidden()

            activation_manager = ActivationManager(env.sim.game_state)

            sequence = []
            turn_reward = 0.0
            turn_start_obs = None

    # safety
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
