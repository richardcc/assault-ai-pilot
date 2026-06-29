R4 CHECKLIST
- [ ] Objetivo único: mejorar vp_stepin_selection_rate con policy redesign.
- [ ] No tocar guardrails adicionales.
- [ ] Implementar cabeza explícita de selección de step-in legal (mask/head auxiliar).
- [ ] Micro-benchmark 20 episodios (seed 42):
      target: vp_stepin_selection_rate >= 0.50
- [ ] Solo si pasa micro-benchmark: subir a 120 episodios.
- [ ] Criterio kill inmediato:
      - selection_rate < 0.35 en 20 eps, o
      - vp_entry_missed_rate >= 0.92

Script operativo:
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_r4_policy_redesign_gate.ps1`
- Genera closeout: `assault_sim/session/reports/sb3_eval/r4_closeout_<timestamp>.json/.md`

Resultado ultimo run:
- closeout: `assault_sim/session/reports/sb3_eval/r4_closeout_20260627T104148Z.json`
- decision: **KILL**
- micro-benchmark (20 eps, seed 42):
  - `vp_stepin_selection_rate = 0.000` (**FAIL** vs target `>= 0.50`)
  - `vp_entry_missed_rate = 0.359` (no dispara kill por missed rate)
- razon de kill: `selection_rate < 0.35`
- accion operativa: no escalar a 120 episodios en este ciclo.
