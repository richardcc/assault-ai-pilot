from __future__ import annotations

from typing import Any, Callable, Dict

from assault_model.core.victory_outcomes import evaluate_scenario_outcome
from assault_bench.transform_ops import to_dict_rows

HEAD_NAMES: tuple[str, ...] = (
    "policy",
    "value",
    "reward",
    "objective",
    "consistency",
    "mcts",
)


def head_state(status: str, reason: str = "") -> Dict[str, str]:
    return {"status": str(status), "reason": str(reason or "")}


def compute_coverage_status(
    heads: Dict[str, Dict[str, str]], *, head_names: tuple[str, ...] = HEAD_NAMES
) -> tuple[str, str]:
    statuses = [str((heads.get(h, {}) or {}).get("status", "none")) for h in head_names]
    if statuses and all(s == "complete" for s in statuses):
        return "complete", ""
    if statuses and all(s == "none" for s in statuses):
        return "none", "no_head_signals_available"
    return "partial", "some_heads_missing_or_not_applicable"


def to_int_or_none(v):
    try:
        if v is None:
            return None
        return int(v)
    except Exception:
        return None


def field(obj, name: str, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def run_policy_mcts(
    *,
    model_kind_local: str,
    kwargs: Dict[str, Any],
    run_mcts_puct_ezv2_fn: Callable[..., Any],
    run_mcts_puct_muzero_fn: Callable[..., Any],
):
    if model_kind_local == "efficientzero_v2":
        return run_mcts_puct_ezv2_fn(**kwargs)
    mz_kwargs = dict(kwargs or {})
    mz_kwargs.pop("q_root_normalization_mode", None)
    mz_kwargs.pop("q_root_normalization_strength", None)
    mz_kwargs.pop("value_rescale_mode", None)
    mz_kwargs.pop("value_rescale_temperature", None)
    mz_kwargs.pop("success_prob_enabled", None)
    mz_kwargs.pop("success_prob_alpha", None)
    mz_kwargs.pop("success_prob_center", None)
    mz_kwargs.pop("success_prob_scale", None)
    mz_kwargs.pop("success_prob_centered_clip_abs", None)
    return run_mcts_puct_muzero_fn(**mz_kwargs)


def scenario_outcome_from_final_vp(
    *,
    final_vp_by_side: Dict[str, int],
    adapter,
    normalize_outcome_score_fn: Callable[[object], int | None] | None = None,
) -> Dict[str, object]:
    runtime = getattr(adapter.sim, "_runtime", None)
    scenario = getattr(runtime, "scenario", None) if runtime is not None else None
    state = getattr(adapter.sim, "_state", None)

    outcome = evaluate_scenario_outcome(
        state=state,
        scenario=scenario,
        final_vp_by_side=final_vp_by_side,
    )
    res = outcome.to_dict()
    if normalize_outcome_score_fn is not None:
        res["outcome_score"] = normalize_outcome_score_fn(res.get("outcome_score"))
    return res


def vp_control_counts(*, adapter) -> Dict[str, int]:
    state = getattr(adapter.sim, "_state", None)
    if state is None:
        return {}
    counts: Dict[str, int] = {}
    side_to_ownership = dict(getattr(state, "side_to_ownership", {}) or {})
    for side in side_to_ownership.keys():
        counts[str(side)] = 0
    victory = getattr(state, "victory", None)
    if victory is None:
        return counts
    for vp in getattr(victory, "points", []) or []:
        hs = state.hex_states.get(vp.hex_coords) if getattr(state, "hex_states", None) else None
        if hs is None:
            continue
        owner = getattr(hs, "ownership", None)
        for side, side_owner in side_to_ownership.items():
            if owner == side_owner:
                side_s = str(side)
                counts[side_s] = counts.get(side_s, 0) + 1
                break
    return counts
