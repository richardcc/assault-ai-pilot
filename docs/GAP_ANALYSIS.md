# Gap Analysis (Vendor vs Implemented vs Pending)

This page tracks convergence between canonical vendor rules and current code.

## Global Validation State

Current documentation pack status: **Pending Validation**.

Closure criteria:

- canonical PDF values transcribed,
- code mappings verified,
- test references completed,
- reviewer approval recorded.

## Priority Legend

- **High**: can change gameplay outcomes or training signals.
- **Medium**: affects fidelity, UX consistency, or edge-case correctness.
- **Low**: documentation, tooling, or non-critical optional parity.

## Current Gaps

| Area | Vendor Expectation | Current Status | Priority | Next Action |
| --- | --- | --- | --- | --- |
| Dice modifier parity (ranged + close combat) | Exact modifier tables and resolution order | Validation framework added in Annex C, canonical values pending transcription | High | Transcribe all chapter 10/11 modifier values and link tests |
| Full chapter-by-chapter parity | 100% mechanics from core + aids + clarifications | Core implemented, some rule edges not explicitly table-traced in code docs | High | Build per-section checklist (rule ID -> module -> test) |
| TAS/OAS edge coverage | Full support including rare branch cases | Main flow present, edge matrix not fully regression-tested | High | Add scenario tests for each TAS/OAS branch |
| Campaign persistence depth | Full campaign lifecycle and branch outcomes | Base structure documented, full parity audit pending | Medium | Add campaign outcome mapping tests |
| Optional FoW completeness | Complete optional module behavior | Feature documented, implementation selective | Medium | Gate + progressive enablement plan with tests |
| Traceability granularity | Direct PDF paragraph to code mapping | Chapter-level mapping available, paragraph-level pending | Medium | Add fine-grain trace table in annex |
| Documentation depth | Implementable spec without assumptions | Improved, still evolving toward exhaustive per-subsection detail | High | Expand chapter subsections with explicit pseudo-rules |
| RL artifact reproducibility hygiene | Fresh model workspace each train run, no stale `models/*` carry-over | Implemented in `train_sb3`, validation run pending | High | Add regression test for startup cleanup + confirm baseline stored outside `models/` |
| `train_sb3` CLI safety (`--help`) | CLI help must exit without starting training side effects | Implemented via `argparse` in `train_sb3`; pending smoke validation in CI | Medium | Add CLI regression test: `python -m assault_sim.train.train_sb3 --help` returns usage and exits 0 without creating run artifacts |
| Parallel eval orchestration | Multi-seed eval acceleration without cross-seed artifact collision | Implemented in `run_train_eval.ps1` with per-seed output isolation; pending field validation | Medium | Validate `42/43/44` parallel run and confirm deterministic gate decision |
| P4.3c override observability | Explicit emergency/legal override counters and reasons in trace/report | Implemented in executor->env->trace->analyzer pipeline, pending mission-level validation | High | Validate on smoke eval and confirm override rates/reasons in final report |
| Turn-wide strategy lock in Gym controller | Per-activation strategy intent to avoid full-turn collapse into weak intent | Implemented by removing turn-level strategy lock; pending tactical validation | High | Run smoke train/eval and compare `true_win_rate`, `loss_rate`, `strategy_stuck_ratio` vs current baseline |
| CAPTURE progress-vs-staging anomaly detection | Detect and break near-VP lateral loops that block objective conversion | Implemented observability counters, progress-priority selection, strict CAPTURE advance, near-VP anti-lateralization fallback (`forced_attack_near_vp_staging`), VP-window opening fallback (`forced_attack_open_vp_window`) widened to `<=3` with lane-opening targets adjacent to uncaptured VP, VP-relevant-only relaxed fallback, short TTL per-unit VP focus lock, per-unit near-VP no-step-in streak, aggressive L3 CAPTURE force (`aggressive_l3_capture_force`), minimum L3 CAPTURE quota (`minimum_capture_intent_quota`), near-VP conversion guardrail, CAPTURE movement shaping toward VP-adjacent ring plus enemy-pressure-aware scoring, CAPTURE+support-fire lane-opening coupling (`attack_gate_support_open_lane`), post-opening follow-up advance + cooldown guardrail, and A/B switch `capture_guardrails_enabled`; pending tactical validation | High | Run ON/OFF smoke eval (`seed=42`, `episodes=60`) and compare fallback mix, VP focus stability, L3 intent distribution, VP-entry conversion, `capture_move_block_profile` quality, `l3_capture_forced_rate/reasons`, `post_open_window_followup_success_rate`, and compare-gate deltas |
| VP-entry funnel blindness (legal step-ins vs selected vs sustained control) | Diagnose where VP conversion collapses despite opportunities | Implemented funnel observability (`vp_stepin_legal_count`, `vp_stepin_selected_count`, `vp_stepin_block_reason_counts`, `vp_no_legal_stepin_near_count`, `vp_nearest_uncaptured_dist`, `vp_control_after_entry_turns_p50/p90`, per-unit entry attempts/success); pending validation | High | Run smoke eval and compare funnel drop-off stage before changing tactics/training |
| R4 step-in policy redesign | Explicit policy-side handling of legal step-in opportunities (mask/head) instead of incremental guardrail forcing | Skeleton implemented (`stepin_legal_mask`, `stepin_forced_option`) in Gym/eval controllers with telemetry aggregation; behavioral impact pending | High | Run micro-benchmark (`seed=42`, `episodes=20`) and gate on `vp_stepin_selection_rate >= 0.50` before full 120-episode eval |

## Backlog Integration

Roadmap should keep these recurring tasks:

1. maintain per-rule trace table,
2. close high-priority parity gaps first,
3. require tests for any claim of "implemented".
