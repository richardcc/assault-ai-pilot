# Notes

Phase files in `configs/` use `base_config` + overrides and are directly executable.

No manual copy is required. Run the cycle manifest as-is.

Available cycle manifests:

- `curriculums/self_vs_self_vs_random_v1/cycle.template.json` (phase1 bootstrap)
- `curriculums/self_vs_self_vs_random_v1/cycles/phase2_mix_70_30.cycle.json`
- `curriculums/self_vs_self_vs_random_v1/cycles/phase3_mix_50_50.cycle.json`
- `curriculums/self_vs_self_vs_random_v1/cycles/phase4_mix_30_70.cycle.json`
- `curriculums/self_vs_self_vs_random_v1/cycles/phase5_self_dominant_90_10.cycle.json`
- `curriculums/self_vs_self_vs_random_v1/cycles/phase6_self_only_stabilize.cycle.json`

Run full curriculum with stop-by-gate:

```powershell
powershell -ExecutionPolicy Bypass -File .\curriculums\self_vs_self_vs_random_v1\run_all_phases.ps1
```

Dry-run:

```powershell
powershell -ExecutionPolicy Bypass -File .\curriculums\self_vs_self_vs_random_v1\run_all_phases.ps1 -DryRun
```
