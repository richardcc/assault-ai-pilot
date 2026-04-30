from assault_sim.policies.registry import PolicyRegistry
from assault_sim.heuristics.noop import NoOpHeuristic
from assault_sim.heuristics.basic import BasicHeuristic

def build_policy_registry() -> PolicyRegistry:
    registry = PolicyRegistry()
    registry.register("noop", NoOpHeuristic())
    registry.register("heuristic_basic", BasicHeuristic())
    return registry