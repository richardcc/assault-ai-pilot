from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from assault_sim.decision.option_executor.capture import OptionExecutorCaptureMixin
from assault_sim.decision.option_executor.combat import OptionExecutorCombatMixin
from assault_sim.decision.option_executor.state import OptionExecutorStateMixin

_legacy_executor_path = Path(__file__).resolve().parents[1] / "option_executor.py"
_legacy_spec = spec_from_file_location("assault_sim.decision._option_executor_legacy", _legacy_executor_path)
if _legacy_spec is None or _legacy_spec.loader is None:
    raise ImportError(f"Cannot load OptionExecutor from {_legacy_executor_path}")
_legacy_module = module_from_spec(_legacy_spec)
_legacy_spec.loader.exec_module(_legacy_module)
OptionExecutor = _legacy_module.OptionExecutor

__all__ = [
    "OptionExecutor",
    "OptionExecutorStateMixin",
    "OptionExecutorCombatMixin",
    "OptionExecutorCaptureMixin",
]
