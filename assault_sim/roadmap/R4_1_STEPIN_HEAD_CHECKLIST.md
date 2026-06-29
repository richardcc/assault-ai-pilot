# R4.1 CHECKLIST — STEP-IN HEAD (single lever)

Objetivo unico:
- subir `vp_stepin_selection_rate` con una sola palanca de policy (sin tocar guardrails adicionales).

Palanca R4.1 (concreta):
- introducir/activar cabeza auxiliar de seleccion de `step-in` legal cuando exista mascara legal de step-in.
- fuera de ese caso, mantener politica actual sin cambios.

Checklist:
- [ ] aplicar solo la palanca R4.1 (sin cambios extra de reward/guardrails/planner).
- [x] micro-benchmark 20 episodios (`seed=42`) con gate:
      - target: `vp_stepin_selection_rate >= 0.50`
      - kill inmediato si `selection_rate < 0.35` o `vp_entry_missed_rate >= 0.92`
- [ ] solo si micro pasa: ejecutar 120 episodios (`seed=42`) con mismo gate.
- [x] registrar closeout y decision final (`GO | NO-GO | KILL`).

Script de ejecucion:
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_r4_1_stepin_head_gate.ps1`

Artefactos esperados:
- `assault_sim/session/reports/sb3_eval/r4_closeout_<timestamp>.json`
- `assault_sim/session/reports/sb3_eval/r4_closeout_<timestamp>.md`

Resultado actual (2026-06-27):
- closeout usado: `assault_sim/session/reports/sb3_eval/r4_closeout_20260627T104848Z.json`
- decision final del ciclo: **KILL**
- lectura operativa:
  - `vp_stepin_selection_rate`: no alcanza target (`>= 0.50`)
  - no escalar a 120 episodios en este ciclo
- estado: ciclo R4.1 cerrado en KILL; mantener baseline `R2.1-i` y no abrir planner avanzado (`P4.3+`) por ahora.
