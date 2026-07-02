from __future__ import annotations

from typing import Dict, List, Optional


def build_episode_narrative(
    rewards: List[float],
    actions: List[str],
    decision_reports: Optional[List[Dict]] = None,
    terminal_reason: str = "",
) -> Dict:
    total_reward = float(sum(rewards))
    unstable_steps = []
    factor_totals: Dict[str, float] = {}
    for report in decision_reports or []:
        step = int(report.get("step", -1))
        instability = report.get("instability", {}) or {}
        if bool(instability.get("unstable", False)):
            unstable_steps.append(step)
        for row in report.get("dominant_factors", []) or []:
            factor = str(row.get("factor", "")).strip()
            if not factor:
                continue
            factor_totals[factor] = factor_totals.get(factor, 0.0) + abs(
                float(row.get("contribution", 0.0))
            )
    dominant_factors = [
        {"factor": k, "weight": float(v)}
        for k, v in sorted(factor_totals.items(), key=lambda kv: kv[1], reverse=True)[:5]
    ]
    return {
        "steps": len(actions),
        "total_reward": total_reward,
        "first_actions": actions[:5],
        "outcome": "terminal_positive" if total_reward > 0 else "neutral_or_negative",
        "terminal_reason": str(terminal_reason or ""),
        "unstable_decision_steps": unstable_steps,
        "unstable_decision_rate": (
            float(len(unstable_steps)) / float(max(1, len(actions)))
        ),
        "dominant_factors": dominant_factors,
        "causal_summary": (
            "Decision process shows instability spikes."
            if unstable_steps
            else "Decision process is stable under current thresholds."
        ),
    }
