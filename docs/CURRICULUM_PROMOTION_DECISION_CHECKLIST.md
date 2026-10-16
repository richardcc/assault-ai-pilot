# Curriculum Promotion Decision Checklist

Objetivo: decidir rapido y de forma consistente `promote`, `hold` o `rollback` al cerrar una fase.

## 1) Inputs minimos

- `phase_name`
- `train_run_id`
- `eval_run_id`
- `gate_spec_snapshot`
- reporte de comparacion vs baseline (script de compare)

## 2) Hard Gate KPIs (bloqueantes)

Si falla cualquiera, **NO promover**.

- `score` cumple umbral de fase.
- `loss_rate` cumple umbral / no-regression (si aplica).
- `xai_vp_capture_take_rate` cumple umbral.
- `tracked_captured_avg` cumple umbral.
- `vp_net_avg_tracked_side` cumple umbral.
- guardrail `vs_random_side_b` no entra en fallo severo.

## 3) Diagnostic KPIs (no bloqueantes)

No bloquean solos, pero pueden forzar `hold` tactico.

- `timeout_rate`
- `non_timeout_resolution_rate`
- `resolved_non_timeout_win_rate`
- velocidad operativa (`episodes_per_second`, `wall_s`, etc.)

Regla:
- Si hard gate = PASS y diagnostico = WARN leve, permitir `promote` con nota.
- Si hard gate = PASS y diagnostico = WARN severo sostenido, usar `hold` 1 iteracion para confirmar estabilidad.

## 4) Decision matrix

- **promote**
  - Hard gate: PASS
  - Sin regresion fuerte en `vs_random_side_b`
  - Riesgo operativo aceptable

- **hold**
  - Hard gate: PASS marginal o diagnostico inestable
  - Necesaria una iteracion corta de confirmacion

- **rollback**
  - Hard gate: FAIL
  - o regresion severa clara frente a baseline

## 5) Registro obligatorio de decision

Guardar siempre en trazabilidad de fase:

- `gate_result_status`
- `gate_fail_reasons`
- `promotion_decision`
- `promotion_reason` (1-2 lineas)
- referencia baseline usada para decidir

## 6) Comandos operativos

Comparar ultimo candidato vs baseline automaticamente:

`powershell -ExecutionPolicy Bypass -File ".\scripts\auto_compare_curriculum_latest.ps1"`

Solo mostrar paths detectados (sin ejecutar compare):

`powershell -ExecutionPolicy Bypass -File ".\scripts\auto_compare_curriculum_latest.ps1" -PrintOnly`
