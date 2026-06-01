from assault_sim.decision.hrl_controller import HRLController
from assault_sim.decision.option_executor import OptionExecutor
from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic


def create_hrl_controller(option_policy, rl_side, event_bus=None):
    """
    Expects an already constructed OptionPolicy.
    """

    # ✅ NO volver a crear OptionPolicy aquí

    heuristic = TacticalPathHeuristic()
    # avoid_bad_trades disabled for baseline/debug behavior
    executor = OptionExecutor(heuristic, avoid_bad_trades=False, adv_threshold=-0.5)

    controller = HRLController(
        option_policy=option_policy,
        option_executor=executor,
        rl_side=rl_side,
        event_bus=event_bus,
    )

    return controller
