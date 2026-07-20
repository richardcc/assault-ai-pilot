# Internal Docs Changelog

Validation state: **Pending Validation**.

## 2026-07-15

- Bench decision telemetry now backfills `why_action_vs_vp` VP progress from observed transition outcomes when action target hex parsing fails.
- Stationary/non-move actions now report `vp_progress_delta=0.0` in VP candidate telemetry instead of `N/A` when VP context exists.
- Added MCTS Q guardrail (`mcts_q_clip_abs`, default `10.0`) for MuZero/EfficientZero selection and backup, plus telemetry counters:
  - `mcts_q_guardrail_clipped_count`
  - `mcts_q_guardrail_clip_limit`
- Added regression tests for VP telemetry fallback/stationary deltas and deterministic Q guardrail clipping behavior.
- EfficientZero v2 root MCTS now applies configurable root-Q normalization (`mcts_q_root_normalization_mode`, `mcts_q_root_normalization_strength`) before Q+U to avoid clipped-Q saturation ties while keeping guardrail clipping telemetry.
- EfficientZero v2 chosen-action selection now applies VP-aware tie-break for near-equal candidate scores (`mcts_vp_tiebreak_epsilon`) and emits explicit tie-break telemetry (`mcts_tiebreak_path`, tie-break metadata in `why_action_vs_vp`).

## 2026-07-03

- Added structured internal docs layout:
  - `mlops/internal_docs/01_architecture/`
  - `mlops/internal_docs/02_operations/`
  - `mlops/internal_docs/03_roadmap/`
- Added section-level README files for each area.
- Added this changelog to track documentation evolution.
- Removed prior top-level legacy files:
  - `mlops/internal_docs/ARCHITECTURE.md`
  - `mlops/internal_docs/OPERATIONS.md`
  - `mlops/internal_docs/ROADMAP.md`
- Added `scripts/run_muzero_train.ps1` for direct MuZero training with optional MLflow run naming.
- Updated operations guide with direct MuZero training commands.
- Added reporting v2 catalog builder:
  - `mlops/reporting/build_catalog.py`
  - `scripts/build_curriculum_reporting_catalog.ps1`
- Reporting v2 now separates `engine/model` identity from `train_history` and `eval_history`, with MLflow commit linkage when available.
- Added base graphical viewer for curriculum reporting:
  - `mlops/reporting/viewer.py`
  - `scripts/run_curriculum_reporting_viewer.ps1`
- Upgraded viewer first UX pass:
  - open in new window option (`-OpenWindow`)
  - selected-train navigation (`Prev`/`Next`)
  - strict engine isolation (no cross-engine train/eval mixing)
