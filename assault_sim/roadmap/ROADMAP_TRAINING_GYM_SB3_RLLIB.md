# ASSAULT SIM — ROADMAP OPERATIVO (LIMPIO)

## Ultima actualizacion (2026-06-27)

## Estado ejecutivo

- pipeline de train/eval estable en Windows
- mejoras de throughput aplicadas y parcialmente validadas
- `R2.1-i` cerrado con **PASS 3/3 seeds** (`42/43/44`, policy `majority`)
- decision vigente: **GO tecnico / GO tactico (baseline operativo nuevo)**

## Objetivo activo

Subir `true_win_rate` y activacion real de captura sin romper estabilidad ni throughput.

## Limites de componente: RAG vs Reglas de juego

- **Reglas de juego (prioridad de entrenamiento)**:
  - autoridad de dinamica tactica, legalidad y resultado de acciones
  - cualquier mejora de RL se valida contra estas reglas y sus metricas

- **RAG (componente de sistema)**:
  - apoyo de explicacion/consulta y analisis
  - no reemplaza los gates de mision ni la validacion tactica del entrenamiento

## Lo ya consolidado

- [x] simplificaciones de codigo y unificacion de finalizer train/eval
- [x] telemetria y trazabilidad suficientes para diagnostico
- [x] optimizaciones de rendimiento con mejora medible de `step_avg_ms`
- [x] varios ciclos R2.1 de palanca unica ejecutados (a-h) con decision formal

## Diagnostico resumido (estado post-cierre R2.1-i)

- gates primarios del ciclo cerraron en PASS agregado
- artefacto de cierre generado: `r21i_closeout_20260627T103609Z.json/.md`
- `R2.1-j` no se abre en este estado (solo aplicaba con NO-GO)

## Priorizacion actual (solo 3 frentes)

1. **R2.1-i: cerrar ciclo activo con evidencia limpia**
   - estado: **completado (GO)**
   - baseline congelado en reportes:
     - `metrics_sb3_report_20260627T103651Z.json`
     - `metrics_sb3_report_20260627T103727Z.json`
     - `metrics_sb3_report_20260627T103759Z.json`

2. **Guardia de baseline (anti-regresion)**
   - mantener mismo protocolo multi-seed para futuras comparativas
   - no abrir `R2.1-j` salvo nueva degradacion material

3. **Cerrar pendientes tecnicos minimos de R2.a**
   - completar gates funcionales faltantes de no-regresion
   - solo continuar optimizacion si reaparece cuello de botella real
   - gate operativo: `scripts/gate_r2a_no_regression_vs_r21i.ps1`

## Reglas operativas (obligatorias)

- una sola palanca por iteracion
- misma bateria de seeds y episodios en todas las comparativas
- no mezclar cambios de planner con reward en el mismo ciclo
- sin mejoras de FPS que degraden primarias tacticas

## Gates de decision vigentes

Primarios:

- `true_win_rate` (objetivo: tendencia al alza sostenida)
- `loss_rate` (sin empeorar materialmente)
- `capture_attempt_success_rate` (debe salir de `0.0`)
- `vp_entry_conversion_rate` (estable por encima del umbral operativo)

Secundarios:

- `strategy_stuck_ratio`
- `captured_final_counts` (masa en `4/5`)

## Ahora mismo (proximo sprint)

- cierre operativo completado con `scripts/cerrar_r21i.ps1` (GO)
- `scripts/preparar_r21j_si_falla.ps1` queda preparado pero **no ejecutar** mientras baseline siga en GO
- ejecutar gate de no-regresion R2.a contra baseline congelado:
  - `powershell -ExecutionPolicy Bypass -File .\scripts\gate_r2a_no_regression_vs_r21i.ps1 -RunEval`

## En pausa explicita

- `P4.3+` (planner avanzado) hasta destrabar conversion tactica por aprendizaje
