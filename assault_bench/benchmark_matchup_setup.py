from __future__ import annotations

from typing import Any, Dict, List


def prepare_matchup_matrix(
    *,
    adapter,
    scenario_id: str,
    seeds: List[int],
    benchmark_cfg: Dict[str, object],
    resolve_enabled_profiles_fn,
    build_profile_defs_fn,
    select_matchup_specs_fn,
) -> Dict[str, Any]:
    base_obs = adapter.initial_state(
        scenario_id=scenario_id, seed=int(seeds[0] if seeds else 0)
    )
    sides = sorted(
        {
            str(u.get("side", "")).strip()
            for u in (getattr(base_obs, "units", []) or [])
            if str(u.get("side", "")).strip()
        }
    )
    if len(sides) < 2:
        active_side = str(getattr(base_obs, "to_play", "") or "").strip()
        if active_side:
            sides = [active_side]
    profile_defs = build_profile_defs_fn(sides)
    enabled_profiles = {
        str(p).strip().lower()
        for p in resolve_enabled_profiles_fn(benchmark_cfg)
    }
    matchup_specs, used_fallback_profiles, available_profiles = select_matchup_specs_fn(
        profile_defs=profile_defs,
        enabled_profiles=enabled_profiles,
    )
    return {
        "sides": sides,
        "profile_defs": profile_defs,
        "enabled_profiles": enabled_profiles,
        "matchup_specs": matchup_specs,
        "used_fallback_profiles": bool(used_fallback_profiles),
        "available_profiles": list(available_profiles or []),
    }

