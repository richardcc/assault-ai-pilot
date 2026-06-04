from dataclasses import dataclass

from assault_model.actions.status import WaitAction
from assault_sim.rl.tactical_options import TacticalOption


@dataclass
class ActionDecisionTrace:
    schema_version: str
    sampled_option: str
    resolved_option: str
    executed_option: str
    strategy: str | None
    was_forced: bool


class ActionBridge:
    TRACE_SCHEMA_VERSION = "1.0.0"
    """
    Bridges policy output to executed domain actions and provides
    a stable trace for training diagnostics.
    """

    def resolve_option(
        self,
        sampled_option: TacticalOption,
        strategy_name: str | None,
        training_mode: bool,
        strict_on_policy: bool = True,
    ) -> TacticalOption:
        # In training, keep policy output untouched unless explicitly disabled.
        if training_mode and strict_on_policy:
            return sampled_option

        if strategy_name is None:
            return sampled_option

        resolved = sampled_option
        if strategy_name == "ATTACK" and sampled_option == TacticalOption.ADVANCE:
            resolved = TacticalOption.ATTACK
        elif strategy_name == "PUSH_VP" and sampled_option == TacticalOption.HOLD:
            resolved = TacticalOption.ADVANCE
        elif strategy_name == "HOLD_VP" and sampled_option == TacticalOption.ADVANCE:
            resolved = TacticalOption.HOLD
        elif strategy_name == "CLEANUP":
            resolved = TacticalOption.ATTACK
        return resolved

    def infer_executed_option(
        self,
        action,
        fallback: TacticalOption,
    ) -> TacticalOption:
        if action is None:
            return TacticalOption.HOLD
        if isinstance(action, WaitAction):
            return TacticalOption.HOLD

        cls = action.__class__.__name__.lower()
        if "ranged" in cls or "assault" in cls or "attack" in cls or "combat" in cls:
            return TacticalOption.ATTACK
        if "move" in cls:
            if fallback == TacticalOption.FLANK:
                return TacticalOption.FLANK
            if fallback == TacticalOption.RETREAT:
                return TacticalOption.RETREAT
            return TacticalOption.ADVANCE
        return fallback

    def build_trace(
        self,
        sampled_option: TacticalOption,
        resolved_option: TacticalOption,
        executed_option: TacticalOption,
        strategy_name: str | None,
    ) -> ActionDecisionTrace:
        return ActionDecisionTrace(
            schema_version=self.TRACE_SCHEMA_VERSION,
            sampled_option=sampled_option.name,
            resolved_option=resolved_option.name,
            executed_option=executed_option.name,
            strategy=strategy_name,
            was_forced=(sampled_option != resolved_option),
        )
