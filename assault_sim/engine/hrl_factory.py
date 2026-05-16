from assault_sim.decision.hrl_controller import HRLController
from assault_sim.decision.option_executor import OptionExecutor
from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic


def create_hrl_controller(option_policy, rl_side, event_bus=None):
    """
    Expects an already constructed OptionPolicy.
    """

    # ✅ NO volver a crear OptionPolicy aquí

    heuristic = TacticalPathHeuristic()
    executor = OptionExecutor(heuristic)

    controller = HRLController(
        option_policy=option_policy,
        option_executor=executor,
        rl_side=rl_side,
        event_bus=event_bus,
    )

    return controller
