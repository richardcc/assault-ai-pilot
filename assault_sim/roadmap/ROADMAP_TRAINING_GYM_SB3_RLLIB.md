# ASSAULT SIM — ROADMAP OPERATIVO (LIMPIO)

## Panel operativo (activo)

Objetivo operativo actual:

- mantener baseline tactico estable y avanzar optimizacion de rendimiento sin degradar gates.

Gates de decision (GO/NO-GO):

- `true_win_rate` no cae y preferiblemente sube
- `loss_rate` no sube materialmente
- `vp_entry_missed_rate` baja de `1.000`
- masa en `captured=4/5` se mantiene o mejora

Checklist inmediato:

- [x] ejecutar R1.b (A/B `dummy|subproc`, `num_envs=4|8`) y decidir configuracion final de rendimiento (`subproc + env4` promovido)
- [x] validar v21 (Mission Planner) con smoke + multi-seed y gate GO/NO-GO (contracto/telemetria OK; impacto tactico aun NO-GO)
- [ ] abrir R2.1 de entrenamiento/reward (salir de techo de guardrails) **[PRIORIDAD ACTIVA]**
- [ ] `reaction_fire` se mantiene OFF hasta cerrar estabilidad post-R1

Regla operativa:

- un solo ajuste por iteracion, misma bateria multi-seed, comparacion contra baseline congelado.

Estado de ejecucion actual:

- baseline tactico congelado: `p43c_main_s424344`
- evidencia consolidada: `subproc` con `num_envs=12` = `NO-GO` tactico
- estado tactico actual (`battaglia_cittadina_2_1`, `120 eps`, `seed 42`):
  - `true_win_rate=0.000`, `loss_rate=0.983`, `NO-GO`
  - embudo VP mejorado pero insuficiente (`vp_stepin_selection_rate=1.0`, `vp_entry_missed_rate~0.877`)
  - conclusion operativa: techo de guardrails; pasar a cambios de entrenamiento/reward

---

## Vision

Construir un sistema robusto de entrenamiento/evaluacion para Assault:

- RL jerarquico estable (`strategy + option + attack_mode + unit_slot`)
- mejora sostenida en captura de VP y victoria real
- trazabilidad total de decisiones (policy vs ejecucion real)
- iteraciones cortas y seguras (`train + eval + trace`)

Importante:

- el orden tactico lo decide el backend (`ActivationManager`/runtime)
- la policy propone; `OptionExecutor` aplica guardrails de mision
- metricas finales mandan: `true_win_rate`, `loss_rate`, `captured_final_counts`

---

## Fase P4 — Agente planificador hibrido (activo)

Problema raiz:

- el agente actual es principalmente reactivo (decision local por paso), con coordinacion limitada entre unidades
- esto explica saturacion en `captured=3`, baja conversion de entrada VP y oscilaciones tacticas

Objetivo P4:

- evolucionar de reactivo jerarquico a hibrido planificador sin perder estabilidad
- combinar guias estructurales (plan/roles/presupuesto) + aprendizaje RL (seleccion y adaptacion)

Principios de diseno:

- [ ] RL sigue decidiendo, pero dentro de un marco de intencion tactica explicita
- [ ] no hardcodear guiones cerrados por escenario
- [ ] guardrails minimos y medibles; toda regla nueva debe tener metrica asociada
- [ ] introduccion incremental: una capacidad de planificacion por iteracion

Arquitectura objetivo:

- [ ] `TeamIntent` (`CAPTURE_PUSH`, `FIX_AND_FLANK`, `PRESERVE_AND_HOLD`, `DENY_COUNTER`)
- [ ] `RoleAssignment` por unidad (`ASSAULT`, `SUPPORT_FIRE`, `SCREEN`, `HOLD_VP`, `RESERVE`)
- [ ] `ActionBudget` por ventana tactica
- [ ] `PlanMemory` (objetivo focal, progreso, fallback, pasos sin progreso)
- [ ] `Coordinator` en `OptionExecutor`

### P4.2 — Team Intent y Role Assignment activos

Entregables:

- [x] selector de `TeamIntent` por contexto (`v25`)
- [x] asignacion de rol por unidad por ciclo de activacion (`role_mapper`, `v25`)
- [x] integracion en scoring L2 (`ADVANCE/ATTACK/RETREAT`) con pesos por rol (`v25`)
- [x] fallback explicito con razon (`intent_blocked`, `budget_exhausted`, `emergency_override`) (`v25`)
- [x] retune aplicado y evaluado (`v25-b`, `v25-c`)

Gates:

- [ ] `strategy_stuck_ratio` baja
- [ ] `vp_entry_missed_rate` baja
- [ ] `forced_ratio` en CAPTURE baja o se mantiene con mejor resultado

Estado de cierre operativo:

- **P4.2 implementado, gate tactico NO-GO** en smoke reciente.
- Resultado observado (`seed=42`, 10 eps, `v25-c`): `true_win_rate=0.000`, `loss_rate=0.600`, `strategy_stuck_ratio=0.509`, `vp_entry_missed_rate=0.615`.
- Decision: congelar mas cambios de guardrail/planner en P4.2 y mover esfuerzo a `R2.1` (aprendizaje/reward).

### P4.3 — Action Budget y anti-oportunismo cerca de VP

Entregables:

- [ ] presupuesto de acciones por intencion por ventana de turno
- [ ] prioridad `entry-first` cerca de VP bajo CAPTURE (sin hard-force global)
- [ ] contador de deuda tactica para subir prioridad de entrada
- [ ] metrica nueva `budget_compliance_rate`

Gates:

- [ ] sube `vp_entry_conversion_rate`
- [ ] mejora masa en `captured=4/5`
- [ ] `damage_ratio` no colapsa materialmente

### P4.4 — Plan Memory multi-step

Entregables:

- [ ] memoria por unidad (`planned_target`, `last_progress`, `last_failure_reason`)
- [ ] memoria de equipo (`focus_vp_id`, `turn_plan_progress`, `units_committed`)
- [ ] anti-loop semantico (no solo A->B->A)
- [ ] features nuevas de observacion derivadas de plan memory (2-4 por iteracion)

Gates:

- [ ] baja `strategy_stuck_ratio` y `vp_entry_missed_rate`
- [ ] sube `capture_attempt_success_rate`
- [ ] estabilidad multi-seed mantenida

### P4.5 — Aprendizaje hibrido

Entregables:

- [ ] reward shaping de coordinacion
- [ ] penalizacion de descoordinacion cerca de VP
- [ ] curriculum: escenarios simples -> mixtos -> completos
- [ ] experimento A/B: reactive baseline vs hybrid planner

Gates:

- [ ] `true_win_rate` mejora sostenida en 42/43/44
- [ ] `loss_rate` no empeora materialmente
- [ ] ganancia neta en metricas de mision

### P4.6 — Planner avanzado (opcional, post-hibrido)

Solo si P4.1-P4.5 cumplen gates:

- [ ] evaluar macro planner horizonte 2-3 turnos (beam/MCTS liviano) como teacher/prior
- [ ] distillation para acelerar entrenamiento de policy
- [ ] mantener fallback al hibrido si falla latencia/estabilidad

### P4.7 — Mission Planner multi-turno (pendiente validacion)

Pendiente de validacion:

- [ ] smoke train/eval (`seed=42`, `episodes=20`) sin degradacion primaria
- [ ] multi-seed (`42/43/44`) con mejora o estabilidad de:
  - `vp_entry_conversion_rate`
  - `true_win_rate`
  - `loss_rate`
- [ ] reduccion de churn:
  - `focus_switch_rate` a la baja
  - `plan_commit_rate` al alza

Metricas nuevas requeridas en `results_analyzer`:

- [ ] `role_diversity_index`
- [ ] `intent_commitment_rate`
- [ ] `budget_compliance_rate`
- [ ] `plan_progress_rate`
- [ ] `coordination_gain`

Backlog tecnico por archivo:

- [ ] `assault_sim/decision/option_executor.py`: coordinator + hooks intent/role/budget/memory
- [ ] `assault_sim/training_env.py`: exponer estado de plan en `info` y observacion
- [ ] `assault_sim/rl/state_encoder.py`: features de coordinacion/plan
- [ ] `assault_sim/evaluation/evaluator.py`: computo de metricas de coordinacion
- [ ] `assault_sim/evaluation/results_analyzer.py`: agregacion/report de nuevas metricas
- [ ] `assault_sim/evaluation/record_sb3_trace.py`: trazas plan step-by-step
- [ ] `assault_sim/tests/`: contratos de roles, budget, memoria y anti-loop semantico

Definicion de exito P4:

- [ ] `true_win_rate` >= baseline P0 + mejora consistente
- [ ] `vp_entry_missed_rate` deja saturacion en `1.000`
- [ ] crecimiento estable de `captured=4/5`
- [ ] reduccion sostenida de decisiones forzadas en CAPTURE

---

## P4.3 — Action Budget (desglose ejecutable)

### P4.3a — Observabilidad de presupuesto (sin enforcement)

- [x] exponer `budget_state`, `budget_remaining_by_role`, `budget_violation_count` en trace/info (`v26`)
- [x] agregar metricas en analyzer: `budget_compliance_rate`, `budget_violation_rate` (`v26`)
- [x] tests de contrato y backward compatibility (`v26`)

Gate P4.3a:

- [x] sin cambios en politica real (solo observabilidad/telemetria)
- [x] reportes y trazas completos (pendiente smoke de confirmacion)

### P4.3c — Hard budget (cuotas duras con escape)

- [x] registro explicito de overrides (`emergency_override`, `legal_override`) en trace/analyzer

Gate P4.3c:

- [ ] GO pleno pendiente: `vp_contact_rate >= 0.20` en agregado multi-seed

---

## Plan de optimizacion de rendimiento (post-GO)

Principio:

- optimizar throughput sin degradar calidad tactica
- cualquier mejora de FPS debe pasar los mismos gates de mision

### R1.b — Protocolo inmediato para subir FPS

Matriz A/B corta:

1. `dummy`, `num_envs=4`
2. `subproc`, `num_envs=4`
3. `dummy`, `num_envs=8`
4. `subproc`, `num_envs=8`

Reglas:

- misma seed y mismo presupuesto por corrida
- no tocar reward/guardrails/policy entre corridas A/B
- registrar: `fps`, `time_elapsed`, `true_win_rate`, `loss_rate`, `vp_entry_conversion_rate`

Gate de promocion:

- [ ] `fps` sube materialmente (>= +25% vs control equivalente)
- [ ] `true_win_rate` no cae materialmente
- [ ] `loss_rate` no sube materialmente
- [ ] `vp_entry_conversion_rate` no empeora claramente

NO-GO automatico:

- [ ] mejora de `fps` con degradacion tactica consistente en primarias

Decision final R1.b:

- si `subproc` pasa gates en `4` y `8`: promover mejor configuracion
- si falla: mantener `dummy` y pasar a optimizacion interna (`R2/R3`)

### Iteracion R2 — Hotspots del simulador

- [ ] perfilar train loop (`cProfile`) para top hotspots reales
- [ ] cachear calculos repetitivos
- [ ] reducir conversiones/serializaciones innecesarias

Gate R2:

- [ ] reduccion medible de tiempo por iteracion
- [ ] sin cambio de comportamiento observable en smoke eval

### Iteracion R3 — Telemetria y modo ejecucion

- [ ] mantener metrica/trazas detalladas en `eval` y `debug`
- [ ] en `train` normal, conservar solo metricas esenciales
- [ ] habilitar flags para activar/desactivar instrumentacion pesada

Gate R3:

- [ ] `fps` sube o se mantiene mejorado
- [ ] reportes de eval siguen completos y compatibles

### Iteracion R4 — Tuning PPO orientado throughput

- [ ] A/B de `n_steps`, `batch_size`, `n_epochs` con ventana estable
- [ ] mantener `approx_kl` y `clip_fraction` en rangos sanos
- [ ] evitar configuraciones que aceleren pero desestabilicen aprendizaje

Gate R4:

- [ ] mejora neta de tiempo total por run
- [ ] metricas de mision al menos iguales al baseline post-P4.2

Checklist de seguridad:

- [ ] comparar contra baseline congelado
- [ ] ejecutar eval multi-seed (`42/43/44`)
- [ ] revisar `true_win_rate`, `loss_rate`, `captured=4/5`, `vp_entry_missed_rate`, `strategy_stuck_ratio`
- [ ] si hay degradacion tactica: revertir optimizacion y pasar a siguiente hipotesis

### Ejecucion paralela configurable (aceleracion segura)

Gates:

- [ ] todos los jobs de seed terminan `exit=0`
- [ ] se generan reportes JSON para todas las seeds pedidas
- [ ] consolidado final mantiene primarias tacticas

Estado:

- [ ] validacion operativa multi-seed en curso (`Pending Validation`)

---

## Simplificacion de codigo (sin compat legacy)

Objetivo:

- reducir complejidad y overhead eliminando rutas legacy que ya no aplican al baseline actual

Paquetes:

- [ ] S1 - Observacion/encoder
- [ ] S2 - Evaluacion/reporting
- [ ] S3 - OptionExecutor
- [ ] S4 - Train lean mode

Gates:

- [ ] tests existentes en verde
- [ ] sin regresion en smoke eval
- [ ] mejora o mantenimiento de FPS

---

## Eliminacion de ficheros no usados

Proceso:

1. Inventario de candidatos
2. Verificacion de uso en codigo/scripts/docs
3. Borrado controlado en lotes pequenos
4. Validacion con tests + smoke train/eval

Checklist:

- [ ] no borrar modelos/reportes activos del experimento en curso
- [ ] no borrar configs usadas por `run_train_eval.ps1`
- [ ] documentar cada borrado relevante
- [ ] si hay duda, mover a `deprecated/` temporal

Estado inicial:

- [ ] preparar inventario de candidatos
- [ ] clasificar por tipo (`legacy_code`, `temp_exports`, `old_reports`, `unused_scripts`)
- [ ] ejecutar primera limpieza controlada post-run

---

## Metricas de gate

Primarias:

- `true_win_rate`
- `loss_rate`
- `captured_final_counts`
- `avg_vp`

Secundarias:

- `draw_rate`
- `strategy_stuck_ratio`
- `damage_ratio`
- `capture_attempt_success_rate`
- `position_reversal_rate`

Umbrales operativos:

- `true_win_rate >= 0.10`
- `loss_rate <= 0.60`
- `strategy_stuck_ratio <= 0.70`
- `vp_entry_missed_rate < 1.00`
- `captured=4/5 >= 1` episodio en `100`
- `position_reversal_rate <= 0.05`

Semaforo:

- GO: cumple umbrales y sin regresion severa
- CONDITIONAL GO: cumple primarios y falla solo un secundario
- NO-GO: falla un primario o hay regresion material multi-seed

---

## Plantilla de decision post-run

- Run id: `<ruta/carpeta>`
- Config: `seeds`, `episodes`, `timesteps`, `obs_shape`
- Resultado agregado:
  - `true_win_rate`
  - `loss_rate`
  - `draw_rate`
  - `vp_entry_missed_rate`
  - `strategy_stuck_ratio`
  - `captured=4/5`
- Gate: `GO | CONDITIONAL GO | NO-GO`
- Razonamiento breve
- Siguiente palanca unica
- Rollback requerido: `si/no`

---

## Siguiente paso

- proximo experimento principal: `R2.1` entrenamiento/reward (dejar micro-guardrails)
- foco R2.1:
  - premiar conversion post-contacto/control sostenido VP
  - penalizar concentracion excesiva (`unit_concentration_index`)
  - reforzar contribucion de soporte en ventanas de captura
- promover cambios solo si preservan/mejoran primarias y reducen `vp_entry_missed_rate`

### Sprint corto R2.1 (para ir tachando rapido)

#### T-telemetry-v1 — afinacion previa a entrenamiento

- [x] causas de `UNKNOWN` en roles (`plan_role_unknown_reason_counts`)
- [x] embudo CAPTURE por rama (`capture_branch_counts`)
- [x] matriz near-VP (`sampled->resolved->action_class`)
- [x] latencias de mision (`turn_first_contact/progress/capture`, `*_delay`)

#### R2.1-a — Reward shaping base (sin cambios de planner)

- [ ] ajustar pesos de reward en `assault_sim/config/reward_config.json` (captura sostenida, post-contacto, concentracion)
- [ ] implementar deltas en `assault_sim/rewards/progressive_reward.py` con banderas claras por componente
- [ ] exponer contribucion por componente en `info`/metricas para auditoria rapida
- [ ] correr smoke `seed=42` (10-20 eps) y registrar decision

Gate de salida R2.1-a:

- [ ] no empeora `loss_rate` ni `position_reversal_rate`
- [ ] baja inicial en `vp_entry_missed_rate` o `strategy_stuck_ratio` (al menos una)

#### R2.1-b — Retune por embudo VP

- [ ] reforzar premio de conversion despues de primer contacto VP (`capture_conversion_after_contact`)
- [ ] penalizar ataques oportunistas cerca de VP cuando no abren entrada (`attack_opportunity_cost_near_vp`)
- [ ] calibrar contribucion de unidades de soporte en ventana CAPTURE
- [ ] correr multi-seed corto (`42/43/44`, 10 eps c/u)

Gate de salida R2.1-b:

- [ ] `vp_entry_missed_rate` baja en agregado multi-seed vs baseline operativo
- [ ] `strategy_stuck_ratio` no sube materialmente

#### R2.1-c — Consolidacion GO/NO-GO

- [ ] corrida de confirmacion (`42/43/44`, 20 eps c/u)
- [ ] completar plantilla de decision post-run en este roadmap
- [ ] decidir `GO | CONDITIONAL GO | NO-GO`
- [ ] solo con GO: reabrir `P4.3`; con NO-GO: nuevo ciclo R2.1 (una sola palanca)

Gate de salida R2.1-c:

- [ ] cumple primarias (`true_win_rate`, `loss_rate`) sin regresion severa
- [ ] mejora mision (`vp_entry_missed_rate` y/o `captured=4/5`) sostenida en agregado

Items pausados para reducir frente activo:

- `P4.3`, `P4.4`, `P4.5`, `P4.6`, `P4.7`: **PAUSADOS** hasta ver mejora real por aprendizaje (`R2.1`).
- mantener solo fixes de estabilidad/telemetria; sin abrir nuevas ramas de planner.
