# P4 v24 Smoke Summary

## Quick Read
- true_win_rate: 0
- loss_rate: 0.7
- vp_entry_conversion_rate: 0.339
- invalid_action_rate: 0
- fallback_rate: 0.583
- wait_recovery_sb3_backstep_rate: 0

## Planner Diagnostics
- intent_commitment_rate_stub: 0.082
- plan_role_counts_stub: UNKNOWN:521, SCREEN:154, ASSAULT:124, SUPPORT_FIRE:94

## Raw Key Lines
- side=US scenario=battaglia_cittadina_2_1 score_win_rate(draw=0.5)=0.150 true_win_rate(only_wins)=0.000 draw_rate=0.300 loss_rate=0.700 avg_vp=4.950 avg_steps=94.8 trade_mean=0.317 damage_ratio=0.550 draws=6 reasons=[objective_outcome_resolved:0.15 (20)] rl_results=[loss:14, draw:6] tracked_results=[Sconfitta totale:6, Sconfitta:8, Pareggio:6]
- interpreted_rates: score_win_rate(draw=0.5)=0.150 true_win_rate(only_wins)=0.000 draw_rate=0.300 loss_rate=0.700
- invalid_action_rate: 0.000
- fallback_rate: 0.583
- wait_recovery_sb3_backstep_rate: 0.000
- vp_entry_conversion_rate: 0.339
- 

## Gate Notes (manual)
- P4 v24 expected direction: intent_commitment up, UNKNOWN role share down.
- R2.1 expected direction: invalid/fallback/wait_backstep rates down.
- Keep NO-GO if loss worsens materially or fallback_rate remains high without mission gains.
