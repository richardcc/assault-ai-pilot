from __future__ import annotations

from typing import Optional


def resolve_prefilter_counts(
    *,
    unit_prefilter_requested: bool,
    active_policy: str,
    raw_unit_prefilter_enabled,
    constrained_from_info: Optional[int],
    global_from_info: Optional[int],
    runtime_constrained_count: int,
    runtime_global_count: int,
) -> dict[str, object]:
    if raw_unit_prefilter_enabled is not None:
        unit_prefilter_enabled = bool(raw_unit_prefilter_enabled)
        unit_prefilter_enabled_source = "transition_info"
    else:
        unit_prefilter_enabled = bool(unit_prefilter_requested)
        unit_prefilter_enabled_source = "runtime_prefilter_flag"
    if (
        bool(unit_prefilter_requested)
        and str(active_policy).strip().lower() != "random"
        and not bool(unit_prefilter_enabled)
    ):
        unit_prefilter_enabled = True
        unit_prefilter_enabled_source = "runtime_prefilter_flag_overrode_transition_false"

    unit_prefilter_constrained_count = constrained_from_info
    if unit_prefilter_constrained_count is None:
        if unit_prefilter_enabled:
            unit_prefilter_constrained_count = int(runtime_constrained_count)
            unit_prefilter_constrained_count_source = "runtime_constrained_legal_count"
        else:
            unit_prefilter_constrained_count = None
            unit_prefilter_constrained_count_source = "missing"
    else:
        unit_prefilter_constrained_count_source = "transition_info"
    if (
        unit_prefilter_enabled
        and unit_prefilter_constrained_count is not None
        and int(unit_prefilter_constrained_count) <= 0
        and int(runtime_constrained_count) > 0
    ):
        unit_prefilter_constrained_count = int(runtime_constrained_count)
        unit_prefilter_constrained_count_source = "runtime_repaired_from_transition_info_zero"

    unit_prefilter_global_count = global_from_info
    if unit_prefilter_global_count is None:
        if unit_prefilter_enabled:
            unit_prefilter_global_count = int(runtime_global_count)
            unit_prefilter_global_count_source = "runtime_global_legal_count"
        else:
            unit_prefilter_global_count = None
            unit_prefilter_global_count_source = "missing"
    else:
        unit_prefilter_global_count_source = "transition_info"
    if (
        unit_prefilter_enabled
        and unit_prefilter_global_count is not None
        and int(unit_prefilter_global_count) <= 0
        and int(runtime_global_count) > 0
    ):
        unit_prefilter_global_count = int(runtime_global_count)
        unit_prefilter_global_count_source = "runtime_repaired_from_transition_info_zero"

    return {
        "unit_prefilter_enabled": bool(unit_prefilter_enabled),
        "unit_prefilter_enabled_source": str(unit_prefilter_enabled_source),
        "unit_prefilter_constrained_count": unit_prefilter_constrained_count,
        "unit_prefilter_constrained_count_source": str(unit_prefilter_constrained_count_source),
        "unit_prefilter_global_count": unit_prefilter_global_count,
        "unit_prefilter_global_count_source": str(unit_prefilter_global_count_source),
    }
