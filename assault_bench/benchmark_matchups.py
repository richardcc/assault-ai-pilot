from __future__ import annotations

from typing import Dict, List

from assault_bench.transform_ops import filter_rows, map_rows, to_dict_rows

DEFAULT_MATCHUP_PROFILES: tuple[str, ...] = (
    "muzero_selfplay",
    "muzero_vs_random_side_a",
    "muzero_vs_random_side_b",
)


def build_profile_defs(sides: List[str]) -> list[dict]:
    side_list = [str(s or "") for s in list(sides or []) if str(s or "").strip()]
    profile_defs: list[dict] = [
        {
            "profile": "muzero_selfplay",
            "agent_name": "muzero_stub",
            "policy": "mcts",
            "policy_by_side": {},
            "group": "selfplay",
            "goal": "MuZero mirror baseline",
        },
        {
            "profile": "random_selfplay",
            "agent_name": "baseline_random",
            "policy": "random",
            "policy_by_side": {},
            "group": "selfplay",
            "goal": "Random mirror sanity baseline",
        },
    ]
    if len(side_list) >= 2:
        side_a, side_b = side_list[0], side_list[1]
        profile_defs.extend(
            [
                {
                    "profile": "muzero_vs_random_side_a",
                    "agent_name": f"muzero_vs_random_{side_a}",
                    "policy": "mcts",
                    "policy_by_side": {side_a: "mcts", side_b: "random"},
                    "group": "head_to_head_role",
                    "goal": f"MuZero as {side_a}, random as {side_b}",
                },
                {
                    "profile": "muzero_vs_random_side_b",
                    "agent_name": f"muzero_vs_random_{side_b}",
                    "policy": "mcts",
                    "policy_by_side": {side_a: "random", side_b: "mcts"},
                    "group": "head_to_head_role",
                    "goal": f"MuZero as {side_b}, random as {side_a}",
                },
            ]
        )
    return profile_defs


def select_matchup_specs(
    *,
    profile_defs: List[Dict[str, object]],
    enabled_profiles: set[str],
) -> tuple[list[dict], bool, list[str]]:
    normalized = {str(p).strip().lower() for p in set(enabled_profiles or set())}
    profile_rows = to_dict_rows(profile_defs)
    matchup_specs = filter_rows(
        profile_rows,
        lambda p: str(p.get("profile", "")).strip().lower() in normalized,
    )
    used_fallback = False
    available_profiles = sorted(
        {
            str(name).strip().lower()
            for name in map_rows(profile_rows, lambda p: p.get("profile", ""))
            if str(name).strip()
        }
    )
    if not matchup_specs:
        used_fallback = True
        default_profiles = set(DEFAULT_MATCHUP_PROFILES)
        matchup_specs = filter_rows(
            profile_rows,
            lambda p: str(p.get("profile", "")).strip().lower() in default_profiles,
        )
    return matchup_specs, used_fallback, available_profiles
