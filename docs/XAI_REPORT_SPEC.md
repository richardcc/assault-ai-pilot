# XAI Report Spec (MuZero on VOEC)

Validation state: **Pending Validation**.

## Outputs

- Decision report (`decision_report.py`)
- Search snapshot (`search_tree_snapshot.py`)
- Episode narrative (`episode_narrative.py`)

## Decision report contract

Required fields:

- `step`
- `top_k[]`
  - `action_id`
  - `score.policy_prob`
  - `score.prior`
  - `score.value`
  - `score.visit_count`
- `margin` (`top1.policy_prob - top2.policy_prob`)
- `entropy`
- `dominant_factors[]` (`factor`, `contribution`)
- `instability`
  - `unstable`
  - `reasons.high_entropy`
  - `reasons.low_margin`
  - `thresholds.entropy_threshold`
  - `thresholds.margin_threshold`

Interpretation:

- High entropy and low margin indicate unstable decisions.
- `dominant_factors` is ordered by absolute contribution.

## Search snapshot contract

Required fields:

- `root.expanded_children`
- `root.snapshot_children`
- `root.total_visits`
- `root.policy_entropy`
- `nodes[]`
  - `action_id`
  - `score.visit_count`
  - `score.policy_prob`
  - `score.prior`
  - `score.value`

Represents the relevant subtree at decision time (root + ranked child nodes).

## Strategy taxonomy reference

MuZero strategy labels shown in reports/dashboards are defined in:

- `docs/MUZERO_STRATEGY_TAXONOMY.md`

The taxonomy maps low-level `action_kind` to strategy buckets (`ADVANCE`,
`HOLD`, `CAPTURE`, `ASSAULT`, `ATTACK`, `OTHER`) and is part of the reporting contract.

## Episode narrative contract

Required fields:

- `steps`
- `total_reward`
- `first_actions`
- `outcome`
- `terminal_reason`
- `unstable_decision_steps`
- `unstable_decision_rate`
- `dominant_factors[]` (`factor`, `weight`)
- `causal_summary`

Summarizes causal patterns over the episode for technical audit.

## Minimal example

```json
{
  "step": 3,
  "top_k": [
    {
      "action_id": "move:u1:1,1",
      "score": {
        "policy_prob": 0.6,
        "prior": 0.5,
        "value": 0.2,
        "visit_count": 15
      }
    }
  ],
  "margin": 0.3,
  "entropy": 0.8979,
  "dominant_factors": [
    { "factor": "vp_pressure", "contribution": 0.7 }
  ],
  "instability": {
    "unstable": false,
    "reasons": { "high_entropy": false, "low_margin": false },
    "thresholds": { "entropy_threshold": 1.2, "margin_threshold": 0.2 }
  }
}
```
