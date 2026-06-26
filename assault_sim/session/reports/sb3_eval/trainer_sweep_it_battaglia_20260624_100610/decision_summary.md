# Trainer Sweep Decision Summary

- Timestamp: 2026-06-24 10:53:14
- Global decision: **GO**
- Promotion allowed: **yes**
- Rollback required: **no**

## Recommended Config

- config: train_config_it_sweep_B.run.json
- side/scenario: IT / battaglia_cittadina_2_1
- true_win_rate_objective: 55
- loss_rate: 0
- vp_entry_missed_rate: 0
- captured_4_5: 11
- decision: GO

## Full Gate Table

| config | side | scenario | true_win_rate_objective | loss_rate | vp_entry_missed_rate | captured_4_5 | decision | rollback_required |
|---|---|---|---:|---:|---:|---:|---|---|
| train_config_it_sweep_C.run.json | IT | battaglia_cittadina_2_1 | 55 | 0 | 0 | 11 | GO | no |
| train_config_it_sweep_B.run.json | IT | battaglia_cittadina_2_1 | 55 | 0 | 0 | 11 | GO | no |
| train_config_it_sweep_A.run.json | IT | battaglia_cittadina_2_1 | 1 | 0 | 1 | 20 | CONDITIONAL GO | no |



