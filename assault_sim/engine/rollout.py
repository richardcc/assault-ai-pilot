import torch

from assault_sim.engine.match_runner import MatchRunner
from assault_sim.decision.decision_engine import DecisionEngine

from assault_model.actions.ranged_direct import RangedDirectAttack
from assault_model.actions.ranged_indirect import RangedIndirectAttack
from assault_model.actions.status import WaitAction

from assault_sim.rl.tactical_options import TacticalOption


# -------------------------------------------------
# ✅ ACTION MAPPING (teacher → L2)
# -------------------------------------------------
def action_to_index(action):

    if isinstance(action, (RangedDirectAttack, RangedIndirectAttack)):
        return TacticalOption.ATTACK.value

    if isinstance(action, WaitAction):
        return TacticalOption.HOLD.value

    return TacticalOption.ADVANCE.value


# -------------------------------------------------
# ✅ ROLLOUT
# -------------------------------------------------
def collect_rollout(env, controller, max_steps, seq_len=8):

    runner = MatchRunner(env, controller=controller)

    # ✅ reset env + controller (MUY IMPORTANTE PARA LSTM)
    obs = runner.reset()
    if hasattr(controller, "reset"):
        controller.reset()

    # ----------------------------------------
    # BUFFERS
    # ----------------------------------------
    obs_buf, actions_buf = [], []
    attack_modes_buf, logp_buf = [], []
    values_buf, rewards_buf, dones_buf = [], [], []
    teacher_actions_buf = []

    sequence = []

    turn_start_obs = None
    turn_reward = 0.0

    step_count = 0

    # ✅ tracked per RL turn
    last_action = 0
    last_attack_mode = 0
    last_logp = torch.zeros(1, dtype=torch.float32)
    last_value = torch.zeros(1, dtype=torch.float32)
    last_teacher = 0

    decision_engine = DecisionEngine()

    # ----------------------------------------
    # MAIN LOOP
    # ----------------------------------------
    while step_count < max_steps or len(sequence) == 0:

        step = runner.step(controller, obs)

        next_obs = step["obs"]
        reward = step["reward"]
        done = step["done"]
        side = step["side"]

        # ----------------------------------------
        # ✅ RL TURN START
        # ----------------------------------------
        if side == controller.rl_side:

            if turn_start_obs is None:
                turn_start_obs = obs

            # ----------------------------------------
            # ✅ TEACHER SIGNAL
            # ----------------------------------------
            teacher_idx = 0
            try:
                intent = decision_engine.compute_intent(env)
                if intent:
                    _, teacher_action = intent
                    teacher_idx = action_to_index(teacher_action)
            except:
                teacher_idx = 0

            last_teacher = teacher_idx

            # ----------------------------------------
            # ✅ CONTROLLER OUTPUT
            # ----------------------------------------
            option = getattr(controller, "current_option", None)
            logp = getattr(controller, "last_logp", None)
            value = getattr(controller, "last_value", None)
            attack_mode = getattr(controller, "current_attack_mode", 0)

            # ✅ option
            if option is not None:
                last_action = option.value if not isinstance(option, int) else option

            # ✅ attack mode (nunca None)
            last_attack_mode = attack_mode if attack_mode is not None else 0

            # ✅ logp (YA tensor)
            if logp is not None:
                last_logp = logp.detach()
            else:
                last_logp = torch.zeros(1, dtype=torch.float32)

            # ✅ value (YA tensor → FIX CLAVE)
            if value is not None:
                last_value = value.detach()  # ✅ CORRECTO
            else:
                last_value = torch.zeros(1, dtype=torch.float32)

            turn_reward += reward

        # ----------------------------------------
        # ✅ RL TURN END
        # ----------------------------------------
        if step.get("is_rl_turn_end", False) and turn_start_obs is not None:

            sequence.append({
                "obs": turn_start_obs,
                "action": last_action,
                "attack_mode": last_attack_mode,
                "logp": last_logp,
                "value": last_value,
                "reward": turn_reward,
                "done": done,
                "teacher": last_teacher,
            })

            # reset turn
            turn_start_obs = None
            turn_reward = 0.0

            # ----------------------------------------
            # ✅ SLIDING WINDOW
            # ----------------------------------------
            if len(sequence) >= seq_len:

                chunk = sequence[:seq_len]
                sequence = sequence[1:]

                obs_buf.extend(x["obs"] for x in chunk)
                actions_buf.extend(x["action"] for x in chunk)
                attack_modes_buf.extend(x["attack_mode"] for x in chunk)
                logp_buf.extend(x["logp"] for x in chunk)
                values_buf.extend(x["value"] for x in chunk)
                rewards_buf.extend(x["reward"] for x in chunk)
                dones_buf.extend(x["done"] for x in chunk)
                teacher_actions_buf.extend(x["teacher"] for x in chunk)

        # ----------------------------------------
        # STEP
        # ----------------------------------------
        obs = next_obs
        step_count += 1

        decision_engine.clear_cache()

        # ----------------------------------------
        # RESET EPISODE
        # ----------------------------------------
        if done:
            obs = runner.reset()

            # ✅ reset LSTM aquí también
            if hasattr(controller, "reset"):
                controller.reset()

            turn_start_obs = None
            turn_reward = 0.0

    # ----------------------------------------
    # ✅ FINAL FLUSH
    # ----------------------------------------
    for x in sequence:
        obs_buf.append(x["obs"])
        actions_buf.append(x["action"])
        attack_modes_buf.append(x["attack_mode"])
        logp_buf.append(x["logp"])
        values_buf.append(x["value"])
        rewards_buf.append(x["reward"])
        dones_buf.append(x["done"])
        teacher_actions_buf.append(x["teacher"])

    return {
        "obs": obs_buf,
        "actions": actions_buf,
        "attack_modes": attack_modes_buf,
        "logp": logp_buf,
        "values": values_buf,
        "rewards": rewards_buf,
        "dones": dones_buf,
        "teacher_actions": teacher_actions_buf,
    }