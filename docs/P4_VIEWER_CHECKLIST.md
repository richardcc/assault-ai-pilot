# P4 Viewer Checklist (Post-Train)

Use this after running:

- `powershell -ExecutionPolicy Bypass -File .\run_post_train_p4_pack.ps1 -Episodes 50 -CandidateTag "p4_candidate"`

Open viewer:

- `python .\scripts\sb3_eval_viewer.py`

## 1) Select the correct report

- Pick the latest `metrics_sb3_report_*.json` matching the strict run.
- Confirm header shows the expected seed and episodes.

## 2) Mission tab (core gates)

Check these first:

- `true_win_rate` (via Training summary cards/rows)
- `loss_rate`
- `vp_entry_conversion_rate`
- `capture_attempt_success_rate`
- `strategy_stuck_ratio`
- `vp_entry_missed_rate`

Plan-memory metrics expected to be present:

- `plan_stuck_steps_mean`, `plan_stuck_steps_p90`
- `plan_steps_since_progress_mean`, `plan_steps_since_progress_p90`
- `plan_planned_target_set_rate`, `plan_planned_target_switch_count`
- `plan_last_failure_reason_counts` (top reason visible)
- `plan_team_turn_progress_mean`
- `plan_team_units_committed_mean`
- `plan_team_focus_vp_set_rate`

Advanced planner telemetry expected to be present:

- `plan_advanced_enabled_rate`
- `plan_advanced_horizon_mean`

## 3) How-To tab sanity check

- Treat single-report `GO` as local signal only.
- Final decision must come from strict multi-seed snapshot + A/B compare.

## 4) Snapshot compare outcome (source of truth)

Run:

- `powershell -ExecutionPolicy Bypass -File .\compare_p4_snapshots.ps1 -BaselineSnapshot "<baseline.json>" -CandidateSnapshot "<candidate.json>"`

Decision policy:

- `GO`: wins up, losses stable/down, capture success up, stuck/missed stable/down.
- `CONDITIONAL GO`: mixed but non-regressive profile.
- `NO-GO`: regressions on tactical core metrics.

## 5) Keep / rollback rule

- If 2/3 seeds degrade on tactical core metrics, rollback last palanca only.
- Keep memory/telemetry instrumentation unless it is the explicit regression source.
