# ASSAULT SIM — ROADMAP OPERATIVO (LIMPIO)

## Ultima actualizacion (2026-06-26)

Resumen ejecutivo:

- train estable en Windows con `DummyVecEnv` + `num_envs=1`; throughput observado muy superior a perfiles previos lentos.
- limpieza `train_lean` aplicada: `TrainingEnv` ahora usa `info` compacto y `OptionExecutor` tagging ligero en ruta de entrenamiento.
- `deepcopy` caliente ya recortado en rutas criticas (fallback a shallow copy donde es seguro).
- R2.a avanzado: vectorizacion NumPy parcial en hotspots (cache geometrica por estado, distancias batch `enemy/vp`, scoring batch en rutas CAPTURE/ADVANCE/FLANK, y recorte de deepcopy dominante en `step-in lookahead` para train lean).
- scripts de benchmark creados en FS: `benchmark_train_perf.ps1` y `benchmark_train_perf_ab.ps1`.
- primer A/B ejecutado, pero invalido para cierre de gate de performance interno (`PerfSamples=0`); requiere rerun con captura PERF valida.
- unificacion train/eval del finalizer de acciones en modulo comun (`assault_sim/decision/action_finalizer.py`) para reducir deuda y evitar divergencia.

Proximos pasos inmediatos:

1. rerun A/B con `benchmark_train_perf_ab.ps1` y validar `PerfSamples > 0` en ambas corridas.
2. cerrar gate R2.a F0 con baseline limpio (`step_avg_ms`, `controller_act_avg_ms`, `executor_avg_ms`).
3. validar impacto de F1 ya aplicado (scoring batch de movimiento) y extender solo si el cuello sigue en `executor_avg_ms`.
4. ejecutar smoke eval post-optimizacion para confirmar no-regresion tactica (`loss_rate`, `vp_entry_conversion_rate`).

Semaforo operativo:

- GREEN: estabilidad de arranque/ejecucion en Windows (`dummy + env1`) y limpieza `train_lean` aplicada.
- YELLOW: R2.a en progreso (mejora de throughput observada con `fps~33`; `step_avg_ms` corregido por ventana y util para lectura; falta cierre formal de gates funcionales multi-seed).
- RED: gate tactico aun abierto hasta confirmar no-regresion en smoke eval post-optimizacion.

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
- [x] abrir/cerrar R2.1-a/b/c con decision formal (**NO-GO** multi-seed)
- [~] ejecutar `R2.1-d` (palanca unica activa) **[PRIORIDAD ACTIVA]**
- [ ] `reaction_fire` se mantiene OFF hasta cerrar estabilidad post-R1

Regla operativa:

- un solo ajuste por iteracion, misma bateria multi-seed, comparacion contra baseline congelado.

Estado de ejecucion actual:

- baseline tactico congelado: `p43c_main_s424344`
- evidencia consolidada: `subproc` con `num_envs=12` = `NO-GO` tactico
- estado de iteracion activa: `R2.1-d` (single lever + diagnostico minimo), planner `P4.3+` congelado
- estado de iteracion activa (actualizado): `R2.1-h` cerrado `NO-GO`; activo `R2.1-i` (rollback conservador + throughput + revalidacion multi-seed)
- estado tactico actual (`battaglia_cittadina_2_1`, `120 eps`, `seed 42`):
  - `true_win_rate=0.000`, `loss_rate=0.983`, `NO-GO`
  - embudo VP mejorado pero insuficiente (`vp_stepin_selection_rate=1.0`, `vp_entry_missed_rate~0.877`)
  - conclusion operativa: techo de guardrails; pasar a cambios de entrenamiento/reward

### Ahora mismo (solo ejecucion)

1. correr `R2.1-d` corto (`42/43/44`, 10 eps c/u) con la palanca unica activa.
2. registrar decision `GO | CONDITIONAL GO | NO-GO` con rollback explicito.
3. no reabrir `P4.3+` salvo GO en primarias.

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

- [x] `fps` sube materialmente (>= +25% vs control equivalente)
- [x] `true_win_rate` no cae materialmente
- [x] `loss_rate` no sube materialmente
- [x] `vp_entry_conversion_rate` no empeora claramente

NO-GO automatico:

- [x] mejora de `fps` con degradacion tactica consistente en primarias (observado para configuraciones agresivas)

Decision final R1.b:

- [x] promover `subproc + env4` como configuracion de rendimiento estable
- [x] declarar `subproc + env12` como `NO-GO` tactico

### Iteracion R2 — Hotspots del simulador

- [~] perfilar train loop (`ASSAULT_PERF_PROFILE`) para top hotspots reales
- [~] cachear calculos repetitivos
- [ ] reducir conversiones/serializaciones innecesarias

#### R2.a — Vectorizacion NumPy (plan de ejecucion)

Objetivo:

- reducir tiempo por `env.step` moviendo calculos calientes de bucles Python a operaciones vectorizadas NumPy

Alcance (sin cambiar logica de juego):

- [x] F0 baseline: guardar `step_avg_ms`, `runner_step_avg_ms`, `executor_avg_ms`, `finalize_avg_ms`, `catalog_avg_ms` con `ASSAULT_PERF_PROFILE=1`
  - [x] scripts de benchmark en FS: `benchmark_train_perf.ps1` y `benchmark_train_perf_ab.ps1`
  - [x] `PerfSamples > 0` validado en corridas limpias (ventana `ASSAULT_PERF_EVERY=10`)
  - [x] `step_avg_ms` corregido a ventana fija (evita deriva acumulada y lecturas infladas)
- [~] F1 distancias/nearest vectorizado:
  - [x] construir arrays `(q,r)` por unidades/objetivos por tick (cache geometrica por estado en `OptionExecutor`)
  - [x] calcular distancias en batch (unit->enemy, unit->vp) en una pasada (NumPy)
  - [~] reutilizar resultados en `nearest_*` y filtros de decision (aplicado en `nearest_uncaptured_vp_dist_*`, presion enemiga y min enemy dist; faltan rutas secundarias)
- [~] F1 scoring de movimiento en batch:
  - [x] extraer destinos candidatos a arrays
  - [x] puntuar candidatos (`objective_progress`, `terrain_score`, distancias) con operaciones vectorizadas en rutas `capture_staging`, `move_closer`, `flank_move`
  - [~] pendiente: extender batch scoring a rutas secundarias fuera de CAPTURE si siguen en hotspot
- [~] F2 ActionCatalog vector-friendly:
  - [x] snapshot por tick (`state._cache_version`) y cache particionado por unidad (`actions/moves/attacks`)
  - [x] filtros reutilizables para candidatos de ataque/movimiento en rutas calientes
  - [x] invalidacion estricta por version/estado para evitar acciones stale
  - [~] pendiente: extender masks compactas a rutas secundarias y validar impacto final
- [ ] F3 LOS/geometria (solo si sigue siendo hotspot):
  - [ ] precalculo/lookup de ray paths relevantes
  - [ ] reducir recomputo LOS por accion

Gates R2.a:

- [ ] mejora minima de `catalog_avg_ms` >= 25% vs baseline F0
- [x] mejora de `step_avg_ms` >= 20% vs baseline F0 (validado tras correccion de medicion por ventana y rerun limpio)
- [ ] sin regresion funcional: mismas acciones legales en tests deterministas (seed fija) para estados de referencia
- [ ] sin degradacion tactica material en smoke eval (`loss_rate`, `vp_entry_conversion_rate`, `capture_conversion_after_contact`)

Entrega por fases:

- [~] PR-1: F0 + F1 distancias
- [~] PR-2: F1 scoring batch
- [ ] PR-3: F2 catalog snapshot + masks
- [ ] PR-4: F3 LOS (condicional)

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

Bloqueador actual de ejecucion:

- [~] falta artefacto `models/scenario_battaglia_cittadina_2_1/side_US/sb3_latest_US.zip` para habilitar smoke eval.
- [x] script operativo listo: `run_eval_multiseed_smoke.ps1` (valida artefacto y corre seeds `42/43/44`).

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

- [x] S1 - Observacion/encoder
  - `state_encoder`: one-hot con index map (`O(1)`) y sin rutas de compat duplicadas.
- [x] S2 - Evaluacion/reporting
  - `Evaluator.__init__` limpia `enemy_controller` legacy no usado.
  - `ResultsAnalyzer.print_report` elimina rama legacy de `action_execution` flat.
- [x] S3 - OptionExecutor
  - resolucion de rol centralizada (`role_mapper.resolve_role_with_reason`).
  - contrato de rol operativo sin `UNKNOWN` en flujo normal de runtime.
  - tagging unificado sin fallbacks dispersos.
- [x] S3.b - Finalizer unificado train/eval
  - modulo comun `assault_sim/decision/action_finalizer.py` para `catalog_priority_action` y `finalize_action`.
  - `GymAssaultEnv` y `SB3EvalController` usan la misma logica de finalizacion/override/debug.
- [~] S4 - Train lean mode (**parcial**)
  - [x] `TrainingEnv`: en `train_lean=true` evita payload pesado de `reward_components`.
  - [x] recorte adicional de telemetria no esencial en ruta `train_lean=true` (info compacto + tagging ligero en `OptionExecutor`).
  - [~] pendiente: validar impacto con A/B limpio y `PerfSamples > 0`.

Gates:

- [ ] tests existentes en verde (bloqueado por test root legacy fuera de `assault_sim/tests`)
- [ ] sin regresion en smoke eval (ultimo smoke NO-GO tactico)
- [ ] mejora o mantenimiento de FPS (medicion pendiente; gate fps interrumpido por BOM en script)

### Siguientes pasos (ejecucion inmediata)

1. **Cerrar gates tecnicos de simplificacion**
   - [ ] ejecutar tests scope estable: `pytest assault_sim/tests assault_model/tests`
   - [ ] rerun smoke eval corto (`episodes=10`, `seed=42`) con `scenario_schedule` deduplicado
   - [ ] rerun gate FPS smoke con escritura JSON UTF-8 **sin BOM**

2. **Cerrar S4 (lean completo)**
   - [x] inventariar campos `info` consumidos por train loop vs solo eval/reporting
   - [x] mover campos exclusivamente analiticos fuera de ruta `train_lean=true`
   - [~] medir impacto en throughput (`fps`/`steps_per_sec`) contra baseline actual

3. **Validar contrato de rol v33**
   - [ ] objetivo: `plan_role_counts_stub.UNKNOWN` ~ 0 en smoke
   - [ ] confirmar que `plan_role_unknown_reason` solo aparece en fallbacks reales (`fallback_*`)
   - [ ] si mejora calidad no aparece, pasar a retune reward (no reabrir guardrails planner)

4. **Decision GO/NO-GO de simplificacion**
   - [ ] **GO**: si tests verdes + smoke sin peor primarias + FPS >= baseline
   - [ ] **NO-GO**: revertir solo deltas que degraden primarias y mantener limpieza estructural segura

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
- estado actual: `R2.1-a` implementado/validado en smoke; **activo ahora `R2.1-b`** para atacar el embudo near-VP sin abrir cambios de planner.

### Sprint corto R2.1 (para ir tachando rapido)

#### T-telemetry-v1 — afinacion previa a entrenamiento

- [x] causas de `UNKNOWN` en roles (`plan_role_unknown_reason_counts`)
- [x] embudo CAPTURE por rama (`capture_branch_counts`)
- [x] matriz near-VP (`sampled->resolved->action_class`)
- [x] latencias de mision (`turn_first_contact/progress/capture`, `*_delay`)
- [x] limpieza de latencias invalidas (sin deltas negativos; contadores de invalidez)
- [x] desglose de recompensa por componentes clave para tuning (`reward_component_means`, `v30`)

#### R2.1-a — Reward shaping base (sin cambios de planner)

- [x] ajustar pesos de reward en `assault_sim/config/reward_config.json` (captura sostenida, post-contacto, concentracion) (`v28`)
- [x] implementar deltas en `assault_sim/rewards/progressive_reward.py` con banderas claras por componente (`v28`)
- [x] exponer contribucion por componente en `info`/metricas para auditoria rapida (`v30`)
- [x] correr smoke `seed=42` (10-20 eps) y registrar decision (`metrics_sb3_report_20260622T085854Z.json`)

Gate de salida R2.1-a:

- [x] no empeora `loss_rate` ni `position_reversal_rate`
- [ ] baja inicial en `vp_entry_missed_rate` o `strategy_stuck_ratio` (al menos una)

Estado operativo R2.1-a:

- **CONDITIONAL NO-GO (impacto)**: implementacion y telemetria OK, sin mejora tactica material en smoke.
- lectura smoke (`seed=42`):
  - `loss_rate=0.600` estable, `position_reversal_rate` estable.
  - `vp_entry_missed_rate=0.615` y `strategy_stuck_ratio=0.509` sin mejora.
  - embudo sigue dominado por `capture_priority_action` y transicion near-VP `CAPTURE:HOLD->ADVANCE->MoveAction`.
- decision: pasar a `R2.1-b` (retune por embudo VP), mantener planner/guardrails congelados.

#### R2.1-b — Retune por embudo VP

- [x] reforzar premio de conversion despues de primer contacto VP (`capture_conversion_after_contact`) (`v28`)
- [x] penalizar ataques oportunistas cerca de VP cuando no abren entrada (`attack_opportunity_cost_near_vp`) (`v28`)
- [x] calibrar contribucion de unidades de soporte en ventana CAPTURE (`v31`)
- [x] `R2.1-b-retune-2` conservador: `trade_weight` restaurado a intermedio (`0.80`), mantener `non_capture_near_vp_penalty`, reducir `capture_support_fire_window_bonus` a la mitad (`v32`)
- [x] `R2.1-b-retune-3` conversion-focused: subir `vp_delta_weight` + `capture_post_contact_progress_move_bonus` y aflojar penalizacion CAPTURE que frenaba avance util (`capture_fallback_attack_penalty`, `capture_no_progress_penalty`, `capture_idle_no_progress_penalty`) (`v34`)
- [x] `eval_sb3` dedup por `scenario id` para evitar resumen/comparativa duplicada en curriculum same-scenario (`v34`)
- [x] correr multi-seed corto (`42/43/44`, 10 eps c/u) (`metrics_sb3_report_20260622T141425Z.json`, `metrics_sb3_report_20260622T141446Z.json`, `metrics_sb3_report_20260622T141506Z.json`)

Gate de salida R2.1-b:

- [ ] `vp_entry_missed_rate` baja en agregado multi-seed vs baseline operativo
- [ ] `strategy_stuck_ratio` no sube materialmente

Estado operativo R2.1-b:

- **NO-GO (multi-seed corto 42/43/44)**.
- lectura agregada:
  - `true_win_rate=0.000` en los 3 seeds; `loss_rate` agregado alto (`0.60/0.60/0.70`).
  - `vp_entry_missed_rate` no mejora (`0.655/0.750/0.750`), `strategy_stuck_ratio` sigue alto (`0.748/0.689/0.695`).
  - `objective_delta_term` y componentes de conversion efectiva (`capture_*`) permanecen sin activacion material.
- decision: cerrar `R2.1-b` como NO-GO y abrir nuevo micro-ciclo R2.1 de **palanca unica** (sin cambios de planner).

#### R2.1-c — Consolidacion GO/NO-GO

- [x] corrida de confirmacion (`42/43/44`, 20 eps c/u) (`metrics_sb3_report_20260622T142012Z.json`, `metrics_sb3_report_20260622T142123Z.json`, `metrics_sb3_report_20260622T142209Z.json`)
- [x] completar plantilla de decision post-run en este roadmap
- [x] decidir `GO | CONDITIONAL GO | NO-GO` (**NO-GO** formal)
- [ ] solo con GO: reabrir `P4.3`; con NO-GO: nuevo ciclo R2.1 (una sola palanca)

Gate de salida R2.1-c:

- [x] cumple primarias (`true_win_rate`, `loss_rate`) sin regresion severa (**fallido**)
- [x] mejora mision (`vp_entry_missed_rate` y/o `captured=4/5`) sostenida en agregado (**fallido**)

Estado operativo R2.1-c:

- **NO-GO formal (multi-seed confirmacion 42/43/44, 20 eps c/u)**.
- lectura agregada:
  - `true_win_rate=0.000` en los 3 seeds; `loss_rate` permanece alto (`0.650/0.650/0.750`).
  - `vp_entry_missed_rate` no mejora (`0.766/0.798/0.800`), `strategy_stuck_ratio` sigue alto (`0.700/0.677/0.677`).
  - `objective_delta_term=0.000` y bonus de conversion post-contacto sin activacion material.
- decision: mantener planner congelado, no reabrir `P4.3+`, abrir `R2.1-d` con **palanca unica**.

#### R2.1-d — Single lever activo (vp_delta_weight only)

- [x] ajustar **solo** `vp_delta_weight` (sin tocar planner/guardrails ni otras recompensas) (`v35`: `10.0 -> 12.0` en `assault_sim/config/reward_config.py/json`)
- [x] habilitar modo diagnostico `eval_sb3 --diagnostic-min-overrides` para separar rendimiento SB3-kept vs coerciones de planner en evaluacion (`v37`)
- [x] `R2.1-d.1` pre-entreno (palanca de legalidad): subir `invalid_action_finalization_penalty` (`0.20 -> 0.50`) para reducir `finalizer_override` por acciones SB3 invalidas (`v39`)
- [~] diagnostico de asimetria por bando (rendimiento/CPU): medir `avg_legal_actions_per_decision` y tiempo medio de generacion de `ActionCatalog.actions()` por lado; reportar antes de comparar throughput o calidad entre bandos (instrumentacion implementada `v44`, pendiente corrida de validacion)
- [x] barrido trainer IT `A/B/C` completado (`trainer_sweep_it_battaglia_20260624_100610`) con eval comparativa + gate + summary/history
- [x] decision sweep IT: **GO** global (`decision_summary.md`), `promotion_allowed=yes`, `rollback_required=no`; recomendada `train_config_it_sweep_B.run.json` (empate tecnico con `C`)
- [ ] entreno corto + eval `42/43/44` (10 eps c/u) en el flujo principal de `R2.1-d`
- [ ] decidir `GO | CONDITIONAL GO | NO-GO` final de `R2.1-d` (gates principales de mision) y registrar rollback requerido

Estado operativo R2.1-d (actualizacion 2026-06-24):

- El pipeline `run_trainer_sweep_it_battaglia.ps1` quedo operativo end-to-end (train -> eval -> gate -> summary/history) tras fixes de invocacion/scripting.
- Resultado del sweep IT: **GO en criterio del barrido** (mejora fuerte en `true_win_rate_objective`, `loss_rate=0`, `vp_entry_missed_rate=0` para B/C).
- Nota de alcance: este GO valida el barrido IT y la toolchain; no sustituye la decision final de `R2.1-d` sobre el baseline principal (US + gates de mision globales).

Estado operativo R2.1-d (cierre US 42/43/44):

- **NO-GO formal** en baseline principal US.
- lectura de gates:
  - `capture_attempt_success_rate`: **FAIL** en `42/43/44` (valor `0.0`, bloqueante).
  - `loss_rate`: PASS estable.
  - `vp_entry_conversion_rate`: señal mixta/no estable (PASS parcial, FAIL parcial).
- decision: cerrar `R2.1-d` y abrir `R2.1-e` con palanca unica enfocada en conversion real.

#### R2.1-e — Single lever (capture conversion trigger only)

Hipotesis unica:

- el agente entra/contesta VP pero no consolida captura; falta incentivo terminal de conversion inmediata en la ventana de contacto.

Palanca unica (sin tocar planner/guardrails):

- aumentar **solo** `actor_captured_vp_now` bonus en `ProgressiveReward` (factor actual `vp_delta_weight * 0.8` -> `vp_delta_weight * 1.2`) para reforzar el evento de captura efectiva sobre señales intermedias.

Ejecucion:

- [x] aplicar ajuste unico en `assault_sim/rewards/progressive_reward.py`
- [x] entreno corto + eval `US`, seeds `42/43/44`, `episodes=10` (`metrics_sb3_report_20260624T090350Z.json`, `metrics_sb3_report_20260624T090419Z.json`, `metrics_sb3_report_20260624T090451Z.json`)
- [x] gatear con los mismos criterios:
  - `capture_attempt_success_rate > 0`
  - `loss_rate < 0.8`
  - `vp_entry_conversion_rate >= 0.30`

Gate de salida R2.1-e:

- [x] **GO** solo si `capture_attempt_success_rate` deja `0.0` en agregado y no degrada `loss_rate`. (**no cumplido**)
- [x] **NO-GO** si `capture_attempt_success_rate` sigue en `0.0`; mantener `P4.3+` pausado y abrir nuevo micro-ciclo de palanca unica. (**cumplido**)

Estado operativo R2.1-e (cierre US 42/43/44):

- **NO-GO formal** (`run_r21e_us_gate.ps1` -> `FAIL 3/3 seeds`).
- lectura agregada:
  - `capture_attempt_success_rate`: `0.0` en `42/43/44` (bloqueante principal).
  - `loss_rate`: PASS en `42/43/44`.
  - `vp_entry_conversion_rate`: señal inestable (PASS en `42/44`, FAIL en `43`).
- decision: cerrar `R2.1-e` y abrir `R2.1-f` con palanca unica de reduccion de `finalizer_override`.

#### R2.1-f — Single lever (finalizer override reduction only)

Hipotesis unica:

- la politica produce demasiadas acciones no ejecutables directamente (`finalizer_override` alto), lo que rompe credit assignment de captura aunque haya contacto VP.

Palanca unica (sin tocar planner/guardrails/reward de captura):

- aumentar **solo** `invalid_action_finalization_penalty` en `assault_sim/config/reward_config.py/json` (`0.50 -> 0.80`) para empujar acciones SB3 legalizables y reducir dependencia de finalizador.

Ejecucion:

- [x] aplicar ajuste unico de `invalid_action_finalization_penalty`
- [x] entreno corto + eval `US`, seeds `42/43/44`, `episodes=10` (`metrics_sb3_report_20260624T090649Z.json`, `metrics_sb3_report_20260624T090715Z.json`, `metrics_sb3_report_20260624T090745Z.json`)
- [x] gatear con criterios existentes + observabilidad de fuente:
  - `capture_attempt_success_rate > 0`
  - `loss_rate < 0.8`
  - `vp_entry_conversion_rate >= 0.30`
  - `source_mix_rates.finalizer_override` a la baja vs `R2.1-e`

Gate de salida R2.1-f:

- [x] **GO** si se activa `capture_attempt_success_rate` (>0 agregado) sin regression material en `loss_rate`. (**no cumplido**)
- [x] **NO-GO** si `capture_attempt_success_rate` sigue en `0.0` o si baja via over-penalizacion con degradacion global. (**cumplido**)

Estado operativo R2.1-f (cierre US 42/43/44):

- **NO-GO formal** (`run_r21e_us_gate.ps1` -> `FAIL 3/3 seeds`; nombre de script heredado, usado como runner multi-seed del ciclo actual).
- lectura agregada:
  - `capture_attempt_success_rate`: `0.0` en `42/43/44` (bloqueante principal sin cambio).
  - `loss_rate`: PASS estable en `42/43/44`.
  - `vp_entry_conversion_rate`: señal mixta (PASS `42/44`, FAIL `43`), sin estabilidad.
- decision: cerrar `R2.1-f` y abrir `R2.1-g` con palanca unica de priorizacion CAPTURE.

#### R2.1-g — Single lever (capture strategy prior only)

Hipotesis unica:

- el agente mantiene buen control defensivo/empate pero no asigna suficiente masa de decision a CAPTURE en ventana util; falta sesgo estrategico directo hacia CAPTURE antes de la conversion.

Palanca unica (sin tocar planner/guardrails/finalizer):

- aumentar **solo** `capture_strategy_bonus` en `assault_sim/config/reward_config.py/json` (`0.60 -> 0.90`) para elevar uso efectivo de L3 CAPTURE sin cambiar otras penalizaciones.

Ejecucion:

- [x] aplicar ajuste unico de `capture_strategy_bonus`
- [x] entreno corto + eval `US`, seeds `42/43/44`, `episodes=10` (`metrics_sb3_report_20260624T095700Z.json`, `metrics_sb3_report_20260624T095723Z.json`, `metrics_sb3_report_20260624T095747Z.json`)
- [x] gatear con criterios existentes + trazas de asignacion:
  - `capture_attempt_success_rate > 0`
  - `loss_rate < 0.8`
  - `vp_entry_conversion_rate >= 0.30`
  - `L3 CAPTURE usage/share` al alza vs `R2.1-f`

Gate de salida R2.1-g:

- [x] **GO** si aparece `capture_attempt_success_rate > 0` en agregado y no degrada `loss_rate`. (**no cumplido**)
- [x] **NO-GO** si CAPTURE share sube pero `capture_attempt_success_rate` sigue en `0.0` (abrir siguiente micro-ciclo de palanca unica). (**cumplido**)

Estado operativo R2.1-g (cierre US 42/43/44):

- **NO-GO formal** (`run_r21e_us_gate.ps1` -> `FAIL 3/3 seeds`).
- lectura agregada:
  - `capture_attempt_success_rate`: `0.0` en `42/43/44` (bloqueante principal sin mejora).
  - `loss_rate`: PASS estable en `42/43/44`.
  - `vp_entry_conversion_rate`: señal mixta/parcial (PASS `42/44`, FAIL `43`), sin estabilidad.
- decision: cerrar `R2.1-g` y abrir `R2.1-h` con palanca unica de priorizacion de conversion post-contacto.

#### R2.1-h — Single lever (post-contact conversion bonus only)

Hipotesis unica:

- CAPTURE gana algo de presencia estrategica, pero no convierte tras contacto; falta empuje directo en el momento de conversion post-contacto.

Palanca unica (sin tocar planner/guardrails/finalizer/pesos globales):

- aumentar **solo** `capture_post_contact_progress_move_bonus` en `assault_sim/config/reward_config.py/json` (`0.70 -> 1.00`) para reforzar decisiones que progresan objetivo despues del primer contacto.

Ejecucion:

- [x] aplicar ajuste unico de `capture_post_contact_progress_move_bonus`
- [x] entreno corto + eval `US`, seeds `42/43/44`, `episodes=10`
- [x] gatear con criterios existentes + activacion de componente:
  - `capture_attempt_success_rate > 0`
  - `loss_rate < 0.8`
  - `vp_entry_conversion_rate >= 0.30`
  - `reward_component_means.capture_post_contact_progress_move_bonus` al alza vs `R2.1-g`

Gate de salida R2.1-h:

- [x] **GO** si `capture_attempt_success_rate > 0` en agregado sin regresion material en `loss_rate`. (**no cumplido**)
- [x] **NO-GO** si `capture_attempt_success_rate` permanece en `0.0` (mantener P4 pausado y abrir siguiente micro-ciclo de palanca unica). (**cumplido**)

Estado operativo R2.1-h (cierre):

- **NO-GO formal** en validaciones recientes.
- lectura agregada:
  - `capture_attempt_success_rate` continua en `0.0` (bloqueante principal).
  - `loss_rate` se mantiene en rango de gate.
  - `vp_entry_conversion_rate` se mantiene cerca del umbral pero inestable (`~0.26-0.33`).
- decision: no promover checkpoint de `R2.1-h`; abrir `R2.1-i` con rollback conservador de guardrails CAPTURE y foco en estabilidad de conversion VP.

#### R2.1-i — Rollback conservador + revalidacion rapida

Hipotesis unica:

- el parche CAPTURE "stepin-heavy" sobrecorrigio y degrado combate global; un rollback parcial + sesgo moderado preserva conversion sin romper `loss_rate/damage_ratio`.

Palanca unica:

- rollback de bloques agresivos en `option_executor_capture.py` (sin prioridad dura de `priority_stepin_setup_move`), manteniendo solo sesgos moderados (`enables_stepin_next`) y filtros previos.

Ejecucion:

- [x] rollback parcial aplicado en `option_executor_capture.py` (quitado bloque agresivo; pesos moderados restaurados).
- [x] optimizacion de throughput aplicada en `train_config.json`:
  - `sb3_vec_env_type: dummy`
  - `sb3_eval_freq: 20000`
  - `sb3_eval_episodes: 5`
- [ ] entreno corto + eval `US`, seeds `42/43/44`, `episodes=10`.
- [ ] gatear con runner actualizado (`PassPolicy=majority`) y captura por `capture_conversion_after_contact`.

Gate de salida R2.1-i:

- [ ] **GO** si `2/3` seeds PASS (policy `majority`) sin regresion material en `loss_rate`.
- [ ] **NO-GO** si `vp_entry_conversion_rate` permanece < `0.30` en `3/3` seeds o si reaparece degradacion fuerte de combate.

Items pausados para reducir frente activo:

- `P4.3`, `P4.4`, `P4.5`, `P4.6`, `P4.7`: **PAUSADOS** hasta ver mejora real por aprendizaje (`R2.1`).
- mantener solo fixes de estabilidad/telemetria; sin abrir nuevas ramas de planner.
