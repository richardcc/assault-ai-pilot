from assault_sim.rl.tactical_options import TacticalOption
from assault_sim.rl.state_encoder import explainable_context

from assault_sim.strategy.formation_strategy import (
    FormationStrategy,
    FormationStrategyEngine,
)

from assault_model.actions.status import WaitAction
from assault_model.actions.action_catalog import ActionCatalog
from assault_model.map.terrain_config import terrain_config

import torch
import torch.distributions as torch_dist
import random


class HRLController:

    OPTION_HORIZON = {
        TacticalOption.ADVANCE: 1,
        TacticalOption.FLANK: 1,
        TacticalOption.ATTACK: 1,
        TacticalOption.HOLD: 1,
        TacticalOption.RETREAT: 1,
    }

    def __init__(self, option_policy, option_executor, rl_side, event_bus=None):
        self.policy = option_policy
        self.executor = option_executor
        self.rl_side = rl_side
        self.event_bus = event_bus

        self.current_option = None
        self.current_attack_mode = None
        self.steps_remaining = -1

        self.formation_engine = FormationStrategyEngine()
        self.last_payload = None

        self.last_logp = torch.tensor(0.0)
        self.last_value = torch.tensor(0.0)

    # -------------------------------------------------
    def _can_attack(self, state, unit):
        actions = ActionCatalog(state, unit, terrain_config).actions()
        return any("Ranged" in a.__class__.__name__ for a in actions)

    # -------------------------------------------------
    # ✅ NUEVO: contexto táctico local
    # -------------------------------------------------
    def _local_advantage(self, state, unit):
        if unit is None or unit.position is None:
            return 0

        friend = 0
        enemy = 0

        for u in state.units:
            if not u.alive or u.position is None:
                continue

            d = abs(u.position.q - unit.position.q) + abs(u.position.r - unit.position.r)
            if d <= 3:
                if u.side == unit.side:
                    friend += 1
                else:
                    enemy += 1

        return friend - enemy

    # -------------------------------------------------
    def _sample_policy(self, obs):
        device = next(self.policy.parameters()).device
        obs_t = torch.tensor(obs, dtype=torch.float32, device=device).unsqueeze(0)

        hidden = self.policy.init_hidden(1, device)

        option_logits, attack_logits, value, _ = self.policy(obs_t, hidden)

        option_dist = torch_dist.Categorical(logits=option_logits)
        attack_dist = torch_dist.Categorical(logits=attack_logits)

        option_sample = option_dist.sample()
        attack_sample = attack_dist.sample()

        logp = (
            option_dist.log_prob(option_sample) +
            attack_dist.log_prob(attack_sample)
        )

        self.last_logp = logp.squeeze()
        self.last_value = value.squeeze()

        option = TacticalOption(option_sample.item())
        attack_mode = attack_sample.item()

        return option, attack_mode

    # -------------------------------------------------
    def choose_action(self, state, unit, obs):

        if unit is None:
            return WaitAction("SYSTEM")

        # -------------------------------------------------
        # ✅ OPTION REUSE
        # -------------------------------------------------
        if self.current_option is not None and self.steps_remaining > 0:

            self.steps_remaining -= 1

            action = self.executor.execute(
                state,
                unit,
                self.current_option,
                self.current_attack_mode,
            )

            if action is None:
                action = WaitAction(unit.unit_id)

            if self.last_payload:
                action.hrl_payload = self.last_payload

            return action

        # -------------------------------------------------
        # ✅ NEW DECISION
        # -------------------------------------------------
        strategy = self.formation_engine.update(state, self.rl_side)
        if strategy is None:
            strategy = FormationStrategy.ATTACK

        ppo_option, attack_mode = self._sample_policy(obs)

        # -------------------------------------------------
        # ✅ CONTEXTO TÁCTICO (🔥 NUEVO CLAVE)
        # -------------------------------------------------
        local_adv = self._local_advantage(state, unit)
        can_attack = self._can_attack(state, unit)

        # -------------------------------------------------
        # ✅ STRATEGY BIAS (reducido y más inteligente)
        # -------------------------------------------------
        if strategy == FormationStrategy.ATTACK:
            if ppo_option != TacticalOption.ATTACK and random.random() < 0.4:
                ppo_option = TacticalOption.ATTACK

        elif strategy == FormationStrategy.CLEANUP:
            if random.random() < 0.5:
                ppo_option = TacticalOption.ATTACK

        elif strategy == FormationStrategy.HOLD_VP:
            if local_adv < 0:
                ppo_option = TacticalOption.HOLD

        # -------------------------------------------------
        # ✅ ATTACK PUSH CONTEXTUAL
        # -------------------------------------------------
        if can_attack:

            if local_adv > 0:
                if random.random() < 0.6:
                    ppo_option = TacticalOption.ATTACK

            elif local_adv == 0:
                if random.random() < 0.35:
                    ppo_option = TacticalOption.ATTACK

            else:
                if random.random() < 0.15:
                    ppo_option = TacticalOption.ATTACK

        # -------------------------------------------------
        # ✅ EXPLORATION CONTROLADA (menos caótica)
        # -------------------------------------------------
        if random.random() < 0.05:
            ppo_option = random.choice(list(TacticalOption))

        # -------------------------------------------------
        # ✅ ASSIGN OPTION
        # -------------------------------------------------
        self.current_option = ppo_option

        if self.current_option == TacticalOption.ATTACK:
            self.current_attack_mode = (
                0 if attack_mode is None else attack_mode
            )
        else:
            self.current_attack_mode = None

        self.steps_remaining = self.OPTION_HORIZON[self.current_option]

        # -------------------------------------------------
        # ✅ PAYLOAD
        # -------------------------------------------------
        payload = {
            "formation": strategy.name if strategy else None,
            "option": self.current_option.name,
            "attack_mode": (
                "INDIRECT" if self.current_attack_mode == 1
                else "DIRECT" if self.current_attack_mode is not None
                else None
            ),
        }

        self.last_payload = payload

        # -------------------------------------------------
        # ✅ EVENT BUS
        # -------------------------------------------------
        if self.event_bus:
            context = explainable_context(
                state,
                rl_side=self.rl_side,
                max_turns=getattr(state, "max_turns", None),
            )

            self.event_bus.emit({
                "type": "HRL_DECISION",
                "payload": {
                    "side": self.rl_side,
                    "option": payload["option"],
                    "attack_mode": payload["attack_mode"],
                    "formation": payload["formation"],
                    "context": context,
                    "turn": state.turn,
                }
            })

        # -------------------------------------------------
        # ✅ EXECUTE
        # -------------------------------------------------
        self.steps_remaining -= 1

        action = self.executor.execute(
            state,
            unit,
            self.current_option,
            self.current_attack_mode,
        )

        if action is None:
            action = WaitAction(unit.unit_id)

        action.hrl_payload = payload

        return action