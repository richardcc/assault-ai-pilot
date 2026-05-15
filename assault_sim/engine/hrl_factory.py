from assault_sim.decision.hrl_controller import HRLController
from assault_sim.decision.option_executor import OptionExecutor
from assault_sim.rl.option_policy import OptionPolicy
from assault_sim.heuristics.tactical_path_heuristic import TacticalPathHeuristic


def make_hrl(policy_net, rl_side, event_bus=None):

    option_policy = OptionPolicy(policy_net)

    # ✅ CLAVE: crear heuristic
    heuristic = TacticalPathHeuristic()

    # ✅ CLAVE: pasarla al executor
    executor = OptionExecutor(heuristic)

    controller = HRLController(
        option_policy=option_policy,
        option_executor=executor,
        rl_side=rl_side,
        event_bus=event_bus,
    )

    return controller
create_hrl_controller = make_hrl
