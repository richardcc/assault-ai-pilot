# 🚀 ASSAULT SIM — ROADMAP OPERATIVO COMPLETO

==================================================
## ⚡ PANEL OPERATIVO (P0 / P0.1)

Objetivo de la iteración:
- recuperar baseline competitivo en US sin abrir nuevas líneas de riesgo.

Gates de decisión (GO/NO-GO):
- `true_win_rate` no cae y preferiblemente sube
- `loss_rate` no sube materialmente
- `vp_entry_missed_rate` baja de `1.000`
- masa en `captured=4/5` se mantiene o mejora

Checklist inmediato:
- [ ] cerrar definición consistente de `vp_entry_missed_rate` vs `capture_conversion_after_contact`
- [ ] reducir `forced_ratio` en CAPTURE sin aumentar `loss_rate`
- [ ] mejorar conversión `captured=3 -> captured=4/5`
- [ ] completar ciclo corto: `train -> eval 42/43/44 -> decisión única`

Regla operativa:
- un solo ajuste por iteración, misma batería multi-seed, comparación contra baseline congelado.

Estado de ejecución actual:
- RUN en curso: `train_sb3 -> eval seed 42/43/44 (100 eps)`
- salida esperada: carpeta `assault_sim/session/reports/sb3_eval/run_*`
- monitor: `pipeline.log` + `heartbeat.txt` (con `elapsed_seconds`)

==================================================
## 🧭 VISIÓN

Construir un sistema robusto de entrenamiento/evaluación para Assault:

- 🧠 RL jerárquico estable (`strategy + option + attack_mode + unit_slot`)
- 🎯 Mejora sostenida en captura de VP y victoria real
- 🔍 Trazabilidad total de decisiones (policy vs ejecución real)
- ⚙️ Iteraciones cortas y seguras (train + eval + trace)

IMPORTANTE:
- El orden táctico lo decide el backend (`ActivationManager`/runtime).
- La policy propone; `OptionExecutor` aplica guardrails de misión.
- Métrica final manda: `true_win_rate`, `loss_rate`, `captured_final_counts`.

==================================================
## 🧱 ARQUITECTURA FINAL (SIM/ML)

Core:
- `SimEnv` (motor de ejecución)
- `RuntimeGameState` (estado autoritativo)
- `ActivationManager` (alternancia por activación)
- `ActionCatalog` + `MovementRules` (acciones legales)

RL stack:
- `GymAssaultEnv`
- `SB3 PPO` (ruta principal)
- `OptionExecutor` (policy -> acción real + guardrails)
- `TrainingEnv` + `ProgressiveReward`

Evaluación/observabilidad:
- `eval_sb3.py` (multi-seed)
- `record_sb3_trace.py` / `analyze_sb3_trace.py`
- `results_analyzer.py` (métricas misión/policy alignment)

==================================================
## 🧭 ARQUITECTURA ACTIVACIONES FLEXIBLES

Objetivo:
- Activaciones alternas flexibles (sin hardcode de bandos)
- Sistema de turnos runtime-driven
- Compatible con training RL, match runner y Web UI

Principios:
- [x] No hardcodear lados (`US`/`GE`) en lógica de turno
- [x] Frontend no decide reglas
- [x] Todo basado en `GameState` + runtime
- [x] Modelo/estado autoritativo como fuente de verdad

Distribución de responsabilidades:
- `assault_model`: reglas de juego, acciones, combate, `GameState` (sin lógica compleja de turnos)
- `RuntimeGameState`: `active_side`, `activated_units`, alternancia de lados, fin de turno (**núcleo**)
- `SimEnv`: ejecutar acciones y emitir eventos (sin decidir activaciones)
- `Controller/Runner`: elegir acción (AI/humano), sin reglas de turno
- `Frontend`: representar estado y aceptar input válido, sin reglas

Implementación:
- [x] Paso 1: `RuntimeGameState` con `sides`, `active_side`, `activated_units`
- [x] Paso 2: alternancia por activación y salto de lado sin unidades activables
- [x] Paso 3: integración con `GymAssaultEnv`/`MatchRunner`/backend UI
- [x] Paso 4: cobertura de tests de regresión de activación multi-bando

==================================================
## 📌 MODELO DE DECISIÓN (CRÍTICO)

No es “la policy ejecuta directo”.

Flujo:
1) Policy samplea acción 4D
2) `OptionExecutor` resuelve opción táctica real con contexto misión
3) Se ejecuta acción legal
4) Se registran:
   - `sampled_option`
   - `resolved_option`
   - `executed_option`
   - debug de captura (`fallback_reason`, `move_block_profile`, distancias)

Guardrail clave actual:
- Anti-ping-pong `A->B->A` (permitido solo si entra a VP no capturado)

==================================================
## 📅 FASE P0 — US Objetivos (CERRADA ✅)

Objetivo:
- estabilizar `true_win_rate >= 0.50` multi-seed sin degradar control de VP.

Pendientes:
- [ ] bajar `draw_rate` sin subir `loss_rate`
- [ ] reducir `strategy_stuck_ratio`
- [ ] mejorar conversión `captured=3 -> captured=4/5`
- [ ] coherenciar/corregir `vp_entry_missed_rate`
- [ ] consolidar baseline antes de activar `reaction_fire`

Pendientes inmediatos (prioridad de ejecución):
1) `vp_entry_missed_rate`: cerrar definición y consistencia con `capture_conversion_after_contact`.
2) bajar `forced_ratio` en CAPTURE sin subir `loss_rate`.
3) subir masa en `captured=4/5` manteniendo `damage_ratio`.

Guardrails P0:
- [ ] evitar loops de `RETREAT` fuera de emergencia
- [x] evitar oscilación posicional `A->B->A`
- [ ] mantener excepción de emergencia real (hp/suppression/amenaza cercana)
- [ ] revisar cálculo de distancias y vecinos (posible inconsistencia) y generalizar lógica de movimiento

### Bloque técnico: Distancias y vecinos (`MovementRules`)
- [ ] auditar cálculo de distancia/vecinos en todo el pipeline (`MovementRules`, heurísticas, reward, evaluator)
- [ ] unificar helpers de distancia/vecindad para evitar divergencia entre módulos
- [ ] generalizar cálculo de vecinos/paths para que no dependa de supuestos de escenario
- [ ] añadir tests de contrato:
  - [x] distancia simétrica y estable
  - [x] vecinos válidos en bordes/mapas irregulares
  - [x] consistencia entre acciones legales y métricas de misión

==================================================
## 📅 FASE P0.1 — Observabilidad RL (en curso)

Línea acordada:
- [x] `own_activated_ratio`
- [x] `enemy_activated_ratio`
- [x] `last_action_type_onehot(5)`
- [ ] Fase 2: contexto VP inmediato por unidad (spec lista)
- [ ] Fase 3: riesgo táctico por ruta/hex (pre-`reaction_fire`)

Regla:
- introducir 2-4 features por iteración + validación multi-seed obligatoria.

Fase 2 (spec propuesta, sin activar todavía):
- `unit_can_enter_uncaptured_vp_now` (0/1): existe movimiento legal del actor a VP no controlado por RL en este paso.
- `unit_nearest_uncaptured_vp_dist_norm` ([0,1]): distancia del actor al VP no capturado más cercano, normalizada por constante de escenario.
- `unit_progress_to_vp_last_step` ([-1,1] clip): `dist_before - dist_after` del actor respecto a objetivo VP local.
- `unit_on_contestable_vp_now` (0/1): actor termina sobre VP no controlado por RL tras la acción.

Criterios de aceptación de Fase 2:
- `vp_entry_missed_rate` baja vs baseline congelado.
- `capture_attempt_success_rate` sube o se mantiene.
- `loss_rate` no empeora materialmente.

==================================================
## 📅 FASE P0.2 — Trazabilidad/Debug (hecho + pendiente)

Hecho:
- [x] Instrumentación corregida: `resolved/executed` reflejan tags reales del `action`
- [x] Nuevos campos de trace:
  - `capture_target_dist_before`
  - `capture_target_dist_after`
- [x] Distinción clara entre distancia global y distancia táctica local

Pendiente:
- [x] cerrar interpretación de `vp_entry_missed_rate` con fórmula única

Definición operativa (única):
- `vp_entry_conversion_rate = vp_entries_taken / vp_entry_opportunities` (si `opportunities > 0`, si no `n/a`)
- `vp_entry_missed_rate = 1 - vp_entry_conversion_rate` (mismo denominador)
- `capture_conversion_after_contact` se calcula aparte sobre eventos de contacto (`contact_to_capture_success / contact_events`)

Tabla de trazabilidad (métrica -> fórmula -> fuente):
- `vp_entry_conversion_rate` -> `vp_entries_taken / vp_entry_opportunities` -> `Evaluator.mission` (agregado en `ResultsAnalyzer.mission_metrics`)
- `vp_entry_missed_rate` -> `1 - vp_entry_conversion_rate` -> `Evaluator.mission` (agregado en `ResultsAnalyzer.mission_metrics`)
- `capture_conversion_after_contact` -> `contact_to_capture_success / contact_events` -> `Evaluator.mission` (agregado en `ResultsAnalyzer.mission_metrics`)
- `forced_ratio` -> `forced_steps / rl_decisions` -> `decision_alignment` (`ActionDecisionTrace.was_forced`)

==================================================
## 📅 FASE P1 — Reglas tácticas (post-P0 estable)

`move/fire`:
- [x] MVP integrado
- [ ] seguir recalibrando para uso útil sin hundir `damage_ratio`

`reaction_fire`:
- [ ] mantener OFF hasta recuperación estable de baseline
- [ ] activar por fases tras gates de P0

==================================================
## 📅 FASE P2 — LOS / Spotting (consolidado)

Estado:
- en progreso (no finalizado)

Fases:
- [x] Fase 1: LOS terreno (`CLEAR/HINDERED/BLOCKED`) integrado
- [ ] Fase 2: ray tracing LOS + acumulación de hindrance
- [ ] Fase 3: interacciones avanzadas de terreno + LOS direccional
- [ ] Fase 4: spotting desacoplado de LOS (Rule 10.5)
- [ ] Fase 5: elevation + indirect LOS + smoke dinámico

Próximos pasos:
- [ ] spotting decay
- [ ] trait `SCOUT` mejora spotting
- [ ] modelo de elevación + hooks LOS

==================================================
## 📅 FASE P3 — Escalado (post-P0)

- [ ] profiling hotspots simulador
- [ ] curriculum de complejidad
- [ ] tuning throughput/paralelismo
- [ ] SLO 24h + eval multi-seed

==================================================
## 📅 FASE P4 — Agente planificador híbrido (NUEVO)

Problema raíz:
- el agente actual es principalmente reactivo (decisión local por paso), con coordinación limitada entre unidades.
- esto explica saturación en `captured=3`, baja conversión de entrada VP y oscilaciones tácticas.

Objetivo P4:
- evolucionar de “reactivo jerárquico” a “híbrido planificador” sin perder estabilidad de entrenamiento.
- combinar guías estructurales (plan/roles/presupuesto) + aprendizaje RL (selección y adaptación).

Principios de diseño:
- [ ] RL sigue decidiendo, pero dentro de un marco de intención táctica explícita.
- [ ] no hardcodear guiones cerrados por escenario; usar señales generales (VP, amenaza, tipo de unidad, activaciones restantes).
- [ ] guardrails mínimos y medibles; toda regla nueva debe tener métrica asociada.
- [ ] introducción incremental: una capacidad de planificación por iteración.

Arquitectura objetivo (Planner Overlay sobre L3/L2):
- [ ] `TeamIntent` (horizonte corto, 1-2 turnos): `CAPTURE_PUSH`, `FIX_AND_FLANK`, `PRESERVE_AND_HOLD`, `DENY_COUNTER`.
- [ ] `RoleAssignment` por unidad (dinámico): `ASSAULT`, `SUPPORT_FIRE`, `SCREEN`, `HOLD_VP`, `RESERVE`.
- [ ] `ActionBudget` por ventana táctica: cupos de acciones por rol/intención (ej. mínimo N avances hacia VP antes de atacar oportunista).
- [ ] `PlanMemory` (estado resumido): objetivo focal, progreso por unidad, razón de fallback, pasos sin progreso.
- [ ] `Coordinator` en `OptionExecutor`: ajusta score/prioridad de opciones usando intent/rol/budget antes del guardrail final.

### P4.1 — Fundaciones de planificación (sin cambiar policy SB3)
Entregables:
- [ ] contrato de datos `PlanState` (serializable en trace/info).
- [ ] módulo `role_mapper` basado en tipo de unidad + estado táctico (no solo tipo estático).
- [ ] etiquetas en trace por decisión: `intent`, `role`, `budget_state`, `plan_step_id`.
- [ ] tests de contrato de `PlanState` y consistencia de roles.

Gates:
- [ ] no degradar `true_win_rate` ni subir `loss_rate` vs baseline P0 estable.
- [ ] `position_reversal_rate` no empeora.
- [ ] trazabilidad completa en `record_sb3_trace`.

### P4.2 — Team Intent y Role Assignment activos
Entregables:
- [ ] selector de `TeamIntent` por contexto (control VP, activaciones restantes, presión enemiga).
- [ ] asignación de rol por unidad por ciclo de activación.
- [ ] integración en scoring L2 (`ADVANCE/ATTACK/RETREAT`) con pesos por rol.
- [ ] fallback explícito con razón (`intent_blocked`, `budget_exhausted`, `emergency_override`).

Gates:
- [ ] `strategy_stuck_ratio` baja.
- [ ] `vp_entry_missed_rate` baja.
- [ ] `forced_ratio` en CAPTURE baja o se mantiene con mejor resultado.

### P4.3 — Action Budget y anti-oportunismo cerca de VP
Entregables:
- [ ] presupuesto de acciones por intención (avance/ataque/hold/retreat) por ventana de turno.
- [ ] regla de prioridad “entry-first” cerca de VP bajo CAPTURE (sin hard-force global).
- [ ] contador de deuda táctica: si no hubo progreso VP, subir prioridad de acciones de entrada.
- [ ] métrica nueva `budget_compliance_rate`.

Gates:
- [ ] sube `vp_entry_conversion_rate`.
- [ ] mejora masa en `captured=4/5`.
- [ ] `damage_ratio` no colapsa materialmente.

### P4.4 — Plan Memory multi-step (coordinación real)
Entregables:
- [ ] memoria por unidad de los últimos K pasos de plan (`planned_target`, `last_progress`, `last_failure_reason`).
- [ ] memoria de equipo (`focus_vp_id`, `turn_plan_progress`, `units_committed`).
- [ ] anti-loop semántico (no solo A->B->A): detectar repeticiones sin progreso objetivo.
- [ ] features nuevas de observación derivadas de plan memory (2-4 por iteración).

Gates:
- [ ] baja `strategy_stuck_ratio` y `vp_entry_missed_rate`.
- [ ] sube `capture_attempt_success_rate`.
- [ ] estabilidad multi-seed mantenida.

### P4.5 — Aprendizaje híbrido (entrenar sobre el plan)
Entregables:
- [ ] reward shaping de coordinación (bonus por cumplimiento de intención + captura colaborativa).
- [ ] penalización de descoordinación (ataques oportunistas de alto coste cerca de VP cuando hay ventana de entrada).
- [ ] curriculum: escenarios simples -> mixtos -> completos.
- [ ] experimento A/B: reactive baseline vs hybrid planner.

Gates:
- [ ] `true_win_rate` mejora sostenida en 42/43/44.
- [ ] `loss_rate` no empeora materialmente.
- [ ] ganancia neta en métricas de misión (`vp_entry_conversion_rate`, `captured=4/5`, `multi_unit_contribution`).

### P4.6 — Preparación para planner avanzado (opcional, post-híbrido)
Solo si P4.1-P4.5 cumplen gates:
- [ ] evaluar “macro planner” de horizonte 2-3 turnos (beam/MCTS liviano) como teacher o prior.
- [ ] distillation: usar recomendaciones del planner para acelerar entrenamiento de policy.
- [ ] mantener modo fallback al híbrido si el planner falla latencia/estabilidad.

Métricas nuevas requeridas en `results_analyzer`:
- [ ] `role_diversity_index` (distribución de roles por episodio).
- [ ] `intent_commitment_rate` (pasos alineados con TeamIntent).
- [ ] `budget_compliance_rate`.
- [ ] `plan_progress_rate` (pasos con progreso hacia objetivo de plan).
- [ ] `coordination_gain` (captura o daño logrado por acciones multi-unidad coordinadas).

Backlog técnico por archivo (orientativo):
- [ ] `assault_sim/decision/option_executor.py`: coordinator + intent/role/budget/memory hooks.
- [ ] `assault_sim/training_env.py`: exposición de estado de plan en `info` y observación.
- [ ] `assault_sim/rl/state_encoder.py`: features de coordinación/plan.
- [ ] `assault_sim/evaluation/evaluator.py`: cómputo de métricas de coordinación.
- [ ] `assault_sim/evaluation/results_analyzer.py`: agregación/report de nuevas métricas.
- [ ] `assault_sim/evaluation/record_sb3_trace.py`: trazas de plan step-by-step.
- [ ] `assault_sim/tests/**`: contratos de roles, budget, memoria y anti-loop semántico.

Secuencia operativa recomendada:
1) ejecutar P4.1 (solo observabilidad y contratos).
2) activar P4.2 + P4.3 en iteraciones separadas (una palanca por run).
3) introducir P4.4 con features mínimas (2-4) + eval multi-seed.
4) entrenar P4.5 (híbrido completo) y decidir GO/NO-GO.

Definición de éxito de P4:
- [ ] `true_win_rate` >= baseline P0 + mejora estadísticamente consistente.
- [ ] `vp_entry_missed_rate` deja de estar saturado en `1.000`.
- [ ] crecimiento estable de `captured=4/5`.
- [ ] reducción sostenida de decisiones forzadas en CAPTURE.

### Sprint ejecutable P4.1 (lista de implementación)

Objetivo de sprint:
- dejar listo el “esqueleto de planificación” (datos + trazabilidad + tests) sin alterar aún el comportamiento táctico final.

Alcance (in scope):
- [ ] contratos y estructuras `PlanState`.
- [ ] mapeo inicial de rol por unidad/contexto (`RoleAssignment`).
- [ ] trazabilidad completa de plan en trace/eval/info.
- [ ] tests de contrato y regresión de no-impacto funcional.

No alcance (out of scope):
- [ ] cambios de reward.
- [ ] cambios de policy architecture SB3.
- [ ] activación de budgets duros o planner de horizonte >1.

Backlog detallado por archivo:
- [ ] `assault_sim/decision/option_executor.py`
  - [ ] añadir `PlanIntent`/`UnitRole` (enums o literales tipados).
  - [ ] construir `plan_state` por decisión: `intent`, `unit_role`, `focus_vp_id`, `plan_step_id`.
  - [ ] inyectar metadata en `action.debug_tags` sin cambiar selección final de acción (modo observabilidad).
  - [ ] fallback seguro a valores por defecto si faltan datos (`UNKNOWN`/`None`).
- [ ] `assault_sim/contracts/training_contracts.py`
  - [ ] definir `TypedDict`/dataclass para `PlanStateContract`.
  - [ ] documentar rangos y nulabilidad de cada campo.
- [ ] `assault_sim/training_env.py`
  - [ ] propagar `plan_state` en `info`.
  - [ ] incluir contadores de calidad de plan (`plan_progress_stub`, `intent_alignment_stub`) en modo diagnóstico.
- [ ] `assault_sim/evaluation/record_sb3_trace.py`
  - [ ] registrar en cada paso: `intent`, `unit_role`, `focus_vp_id`, `plan_step_id`.
  - [ ] validar compatibilidad backward con traces previas (campo opcional cuando no exista).
- [ ] `assault_sim/evaluation/evaluator.py`
  - [ ] agregar acumuladores básicos P4.1: `intent_commitment_rate_stub`, `role_diversity_index_stub`.
  - [ ] no usar todavía en gates primarios (solo observabilidad).
- [ ] `assault_sim/evaluation/results_analyzer.py`
  - [ ] mostrar bloque “PLANNING (P4.1 diagnostics)” sin romper reportes anteriores.
  - [ ] defaults robustos si métricas no están presentes.

Tests mínimos obligatorios:
- [ ] `assault_sim/tests/test_plan_state_contracts.py`
  - [ ] esquema válido cuando hay acción.
  - [ ] esquema válido en fallback/sin foco VP.
  - [ ] serialización JSON estable.
- [ ] `assault_sim/tests/test_option_executor_plan_tags.py`
  - [ ] `action` sale con tags de plan en decisiones normales.
  - [ ] no cambia tipo de acción elegida respecto a baseline en fixtures equivalentes.
- [ ] `assault_sim/tests/test_trace_plan_fields.py`
  - [ ] el recorder persiste campos P4.1.
  - [ ] parser tolera ausencia de campos (compat backward).

Checklist de ejecución (orden):
1) implementar contratos (`training_contracts`) y tipos en `option_executor`.
2) cablear propagación a `training_env` + `record_sb3_trace`.
3) exponer diagnósticos en `evaluator` + `results_analyzer`.
4) correr tests unitarios P4.1.
5) correr smoke eval corto (`seed=42`, `episodes=20`) y confirmar no-regresión.

Comandos de validación sugeridos:
- `python -m pytest assault_sim/tests/test_plan_state_contracts.py assault_sim/tests/test_option_executor_plan_tags.py assault_sim/tests/test_trace_plan_fields.py -q`
- `python -m assault_sim.evaluation.eval_sb3 --seed 42 --episodes 20`
- `python -m assault_sim.evaluation.record_sb3_trace --seed 42 --episodes 1`

Criterios de aceptación de sprint:
- [ ] tests nuevos en verde.
- [ ] reporte de evaluación imprime bloque P4.1 diagnostics sin errores.
- [ ] trace contiene campos de plan por paso.
- [ ] variación de `true_win_rate`/`loss_rate` en smoke dentro de banda de ruido (sin degradación evidente).

Riesgos P4.1 + mitigación:
- riesgo: romper compatibilidad de JSON de trazas.
  - mitigación: campos opcionales + defaults en analyzer/reader.
- riesgo: acoplar contrato a una sola táctica.
  - mitigación: enums abiertos + `UNKNOWN`.
- riesgo: introducir sesgo funcional accidental.
  - mitigación: modo observabilidad (sin alterar scoring final) + test de no-regresión funcional.

### Paquete de visibilidad para planificación (P4.2 features)

Objetivo:
- dar “visión útil de plan” (mapa/terreno/progreso/riesgo) sin saturar la observación con ruido.

Regla de implementación:
- introducir en lotes de 4-6 features por iteración.
- normalizar todo a rangos acotados (`[0,1]` o `[-1,1]`).
- cada lote debe pasar eval multi-seed antes del siguiente.

Lote A — Macro objetivo VP (prioridad máxima):
- [x] `focus_vp_dist_norm` `[0,1]`: distancia de unidad activa al VP foco / `MAX_DIST`.
- [x] `focus_vp_progress_last_step` `[-1,1]`: `dist_before - dist_after`, clip.
- [x] `focus_vp_reachable_now` `{0,1}`: existe acción legal que reduce distancia al VP foco.
- [x] `focus_vp_enterable_now` `{0,1}`: existe acción legal que entra a VP no controlado.

Lote B — Riesgo táctico y terreno:
- [x] `hex_risk_current` `[0,1]`: riesgo esperado en hex actual (amenaza agregada enemiga).
- [x] `hex_risk_best_progress_path` `[0,1]`: riesgo mínimo entre paths que progresan a VP.
- [x] `terrain_mobility_cost_norm` `[0,1]`: coste terreno del mejor paso progresivo.
- [x] `los_exposure_next_hex` `[0,1]`: exposición LOS estimada del siguiente hex recomendado.

Lote C — Coordinación de equipo:
- [x] `allies_supporting_focus_ratio` `[0,1]`: proporción de aliados comprometidos con VP foco.
- [x] `role_quota_remaining_norm` `[0,1]`: presupuesto restante para rol actual en ventana táctica.
- [x] `own_unactivated_ratio` `[0,1]`: activaciones propias restantes/total (ya disponible, mantener).
- [x] `enemy_unactivated_ratio` `[0,1]`: activaciones enemigas restantes/total (ya disponible, mantener).

Lote D — Memoria de plan:
- [x] `unit_stuck_steps_norm` `[0,1]`: pasos consecutivos sin progreso VP (normalizado y cap).
- [x] `plan_commitment_age_norm` `[0,1]`: antigüedad de compromiso con `focus_vp`.
- [x] `last_failure_reason_onehot_4` `{0,1}x4`: `blocked`, `high_risk`, `forced`, `no_legal_progress`.
- [x] `intent_alignment_last_k` `[0,1]`: proporción de últimas `k` acciones alineadas con intent.

Lote E — Oportunidad vs oportunismo (anti-desvío):
- [x] `attack_opportunity_cost_near_vp_norm` `[0,1]`: coste de atacar ahora vs avanzar a VP. *(observability-only)*
- [x] `capture_window_open` `{0,1}`: ventana favorable de entrada VP (baja amenaza + legalidad). *(observability-only)*
- [x] `expected_vp_swing_if_advance` `[-1,1]`: cambio esperado de control VP por avanzar. *(observability-only)*
- [x] `expected_trade_if_attack` `[-1,1]`: trade esperado si se elige ataque. *(observability-only)*

Orden recomendado de activación:
1) Lote A (obligatorio primero).
2) Lote C (coordinación mínima).
3) Lote B (riesgo/terreno).
4) Lote D (memoria).
5) Lote E (refinamiento de decisión).

Criterios de aceptación por lote:
- [ ] no empeora `loss_rate` materialmente.
- [ ] mejora o mantiene `true_win_rate`.
- [ ] baja `vp_entry_missed_rate` o sube `vp_entry_conversion_rate`.
- [ ] no sube `position_reversal_rate`.

Cambios de código esperados para estas features:
- [ ] `assault_sim/rl/state_encoder.py`: ampliar vector y orden canónico de features.
- [ ] `assault_sim/training_env.py`: calcular features por paso y reset.
- [ ] `assault_sim/decision/option_executor.py`: exponer `focus_vp`, razones de fallback, progreso.
- [ ] `assault_sim/evaluation/evaluator.py`: medir impacto por lote.
- [ ] `assault_sim/evaluation/results_analyzer.py`: reporte por lote activado.

## 🧪 Matriz de validación por subfase (P4)

### P4.1 — Contratos + trazabilidad (activa)
- Objetivo:
  - introducir `PlanState` y tags de planificación sin cambiar decisión táctica final.
- Pruebas:
  - `test_plan_state_contracts.py` (schema/rangos/nullability).
  - `test_option_executor_plan_tags.py` (tags presentes + no regresión funcional en fixtures).
  - `test_trace_plan_fields.py` (persistencia y backward compatibility).
- Gate GO:
  - tests en verde + trace con campos P4.1 + smoke eval sin degradación clara.
- Gate NO-GO:
  - ruptura de compatibilidad de trace/report o caída material de `true_win_rate`.

### P4.2 — Visibilidad de planificación (lotes A-E)
- Objetivo:
  - añadir contexto útil de mapa/terreno/progreso/riesgo con features normalizadas.
- Pruebas:
  - tests de rango/normalización por feature.
  - test de presencia en observación (`state_encoder`) y `info` (`training_env`).
  - eval por lote activado (A/B contra baseline congelado).
- Gate GO:
  - mejora en `vp_entry_conversion_rate` o baja de `vp_entry_missed_rate`, sin subir `loss_rate`.
- Gate NO-GO:
  - inestabilidad PPO, aumento sostenido de `loss_rate`, o ruido sin ganancia táctica.
 - Nota operativa crítica:
  - tras activar A+B+C+D+E, la observación cambió de `(70,)` a `(74,)`.
  - cualquier modelo/VecNormalize previo a P4.2 es incompatible para evaluación directa.
  - se requiere reentrenamiento completo para generar baseline válido con nuevo encoder.

### P4.3 — Action Budget
- Objetivo:
  - controlar oportunismo y reforzar prioridad de entrada VP en CAPTURE.
- Pruebas:
  - tests de presupuesto (`consume/reset/exhaust/fallback`).
  - trazas con `budget_state` y razones de override.
  - regresión de guardrails (`RETREAT` solo emergencia, anti-loop).
- Gate GO:
  - sube `captured=4/5` y `vp_entry_conversion_rate`; `damage_ratio` estable.
- Gate NO-GO:
  - caída de letalidad o aumento de `forced_ratio` sin mejora de misión.

### P4.4 — Plan Memory multi-step
- Objetivo:
  - sostener intención multi-paso y cortar loops semánticos sin progreso.
- Pruebas:
  - tests de memoria por unidad/equipo (`focus_vp`, progreso, failure_reason).
  - tests anti-loop semántico (no repetir patrón improductivo).
  - validación de nuevas features de memoria (2-4 por iteración).
- Gate GO:
  - baja `strategy_stuck_ratio`, sube `capture_attempt_success_rate`.
- Gate NO-GO:
  - sobre-restricción (agente rígido) o degradación multi-seed.

### P4.5 — Entrenamiento híbrido
- Objetivo:
  - aprender coordinación encima del marco de plan (guidance + RL).
- Pruebas:
  - A/B: baseline reactivo vs híbrido (`seed 42/43/44`).
  - corrida corta + corrida extendida con mismo protocolo.
  - revisión de estabilidad (`NaN/inf`, reward drift, varianza entre seeds).
- Gate GO:
  - mejora sostenida de `true_win_rate` y/o `captured=4/5` sin empeorar `loss_rate`.
- Gate NO-GO:
  - mejora no reproducible o fuerte sensibilidad a seed/configuración.

### P4.6 — Planner avanzado (opcional)
- Objetivo:
  - evaluar planner 2-3 turnos como teacher/prior sin romper latencia/robustez.
- Pruebas:
  - benchmark de latencia y throughput.
  - comparación táctica vs P4.5 (mismas seeds y escenarios).
  - test de fallback automático a híbrido ante fallo del planner.
- Gate GO:
  - ganancia neta clara (calidad táctica + costo computacional aceptable).
- Gate NO-GO:
  - costo alto sin mejora consistente; mantener P4.5 como ruta productiva.

==================================================
## ✅ ESTADO ACTUAL (snapshot)

Ya tienes:
- motor táctico completo
- pipeline SB3 estable
- selección de unidad por policy
- fix anti-ping-pong
- trazas fiables (sampled/resolved/executed + distancias locales)
- P4.2 completo (A+B+C+D+E en observability-first)
- suite de tests de encoder/plan en verde (`12 passed`)
- observación vigente del agente: `shape=(74,)`

Estado de transición:
- P0 cerrada; baseline congelado para comparación.
- fase activa actual: P4.1 (contratos + trazabilidad de planificación).
- fase activa operativa: rebaseline post-P4.2 (retrain + eval multi-seed).
- ejecución en curso: train principal P4.2 (`seed 42/43/44`, encoder `shape=(74,)`).
- estado esperado al cierre de run: decisión GO/NO-GO + siguiente palanca única.

==================================================
## 📊 MÉTRICAS DE GATE

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

==================================================
## 🚦 GO / NO-GO (iteración corta)

GO:
- `true_win_rate` sube o se mantiene
- `loss_rate` no empeora materialmente
- masa en `captured=4/5` se mantiene o mejora

NO-GO:
- caída consistente de `true_win_rate`
- subida sostenida de `loss_rate`
- retorno a saturación en `captured=3`

Regla:
- preferir ciclos cortos: train -> eval -> trace -> ajuste único.

Umbrales operativos (rebaseline P4.2):
- `true_win_rate >= 0.10` (mínimo de aceptación; objetivo de mejora iterativa posterior).
- `loss_rate <= 0.60`.
- `strategy_stuck_ratio <= 0.70`.
- `vp_entry_missed_rate < 1.00` (no aceptar saturación).
- `captured=4/5 >= 1` episodio en `100` (mínimo no-degenerado).
- `position_reversal_rate <= 0.05`.

Semáforo de decisión:
- GO: cumple todos los umbrales y no hay regresión severa vs baseline congelado.
- CONDITIONAL GO: cumple primarios (`true_win_rate`, `loss_rate`) y falla solo un secundario.
- NO-GO: falla cualquier primario o hay regresión material multi-seed.

## 🧾 Plantilla de decisión post-run

Completar al finalizar cada corrida principal:
- **Run id**: `<ruta/carpeta>`
- **Config**: `seeds`, `episodes`, `timesteps`, `obs_shape`
- **Resultado agregado**:
  - `true_win_rate`:
  - `loss_rate`:
  - `draw_rate`:
  - `vp_entry_missed_rate`:
  - `strategy_stuck_ratio`:
  - `captured=4/5`:
- **Gate**: `GO | CONDITIONAL GO | NO-GO`
- **Razonamiento breve**:
- **Siguiente palanca única**:
- **Rollback requerido**: `sí/no`

## 📅 P4.3 — Action Budget (desglose ejecutable)

Objetivo:
- reducir oportunismo cerca de VP y aumentar consistencia de entrada/captura sin rigidizar el agente.

### P4.3a — Observabilidad de presupuesto (sin enforcement)
- [ ] exponer `budget_state`, `budget_remaining_by_role`, `budget_violation_count` en trace/info.
- [ ] agregar métricas en analyzer: `budget_compliance_rate`, `budget_violation_rate`.
- [ ] tests de contrato y backward compatibility.

Gate P4.3a:
- [ ] sin cambios en política real.
- [ ] reportes y trazas completos.

### P4.3b — Soft budget (penalización leve / prioridad suave)
- [ ] prioridad suave a acciones de entrada VP cuando presupuesto de avance está disponible.
- [ ] penalización suave a ataques oportunistas cuando hay ventana de captura.
- [ ] mantener fallback por emergencia.

Gate P4.3b:
- [ ] `vp_entry_conversion_rate` sube o `vp_entry_missed_rate` baja.
- [ ] `loss_rate` no empeora materialmente.

### P4.3c — Hard budget (cuotas duras con escape)
- [ ] activar cuotas mínimas por intención/rol por ventana táctica.
- [ ] escape hatch por emergencia y bloqueo legal.
- [ ] registro explícito de overrides (`emergency_override`, `legal_override`).

Gate P4.3c:
- [ ] sube masa en `captured=4/5`.
- [ ] no colapsa `damage_ratio`.
- [ ] `strategy_stuck_ratio` no empeora.

==================================================
## 🧪 Riesgos y validación de rendimiento

Riesgos:
- no determinismo por `n_envs`
- desalineación obs/reward por estado compartido
- inestabilidad PPO por batch efectivo
- mejoras de FPS con empeoramiento táctico

Protocolo:
- baseline congelado
- A/B corto (`1 env`, `4 envs`, `8 envs`)
- sanity checks (NaN/inf, EV, reward)
- comparar contra gates P0

## ⚙️ Plan de optimización de rendimiento (post-GO)

Principio:
- optimizar throughput **sin degradar calidad táctica**.
- cualquier mejora de FPS debe pasar los mismos gates de misión.

Orden de ejecución recomendado:
1) Paralelismo de entornos (`n_envs`) con A/B controlado.
2) Reducción de overhead en `step` (cache y cálculos repetidos).
3) Separación de telemetría pesada (train vs eval/debug).
4) Tuning PPO para throughput estable.
5) Perfilado dirigido + micro-optimizaciones finales.

### Iteración R1 — Escalado por paralelismo
- [ ] correr matriz A/B: `n_envs in {1, 4, 8}` con misma semilla/protocolo.
- [ ] medir `fps`, `time_elapsed`, `approx_kl`, `explained_variance`.
- [ ] registrar varianza entre seeds para detectar inestabilidad.

Gate R1:
- [ ] `fps` mejora materialmente.
- [ ] `true_win_rate` no cae materialmente.
- [ ] `loss_rate` no sube materialmente.

### Iteración R2 — Hotspots del simulador
- [ ] perfilar train loop (`cProfile`) para top hotspots reales.
- [ ] cachear cálculos repetitivos (distancias, legalidad, evaluaciones locales por tick).
- [ ] reducir conversiones/serializaciones innecesarias en ciclo interno.

Gate R2:
- [ ] reducción medible de tiempo por iteración.
- [ ] sin cambio de comportamiento observable en smoke eval.

### Iteración R3 — Telemetría y modo ejecución
- [ ] mantener métricas/trazas detalladas en `eval` y `debug`.
- [ ] en `train` normal, conservar solo métricas esenciales.
- [ ] habilitar flags para activar/desactivar instrumentación pesada.

Gate R3:
- [ ] `fps` sube o se mantiene mejorado.
- [ ] reportes de eval siguen completos y compatibles.

### Iteración R4 — Tuning PPO orientado throughput
- [ ] A/B de `n_steps`, `batch_size`, `n_epochs` con ventana estable.
- [ ] mantener `approx_kl` y `clip_fraction` en rangos sanos.
- [ ] evitar configuraciones que aceleren pero desestabilicen aprendizaje.

Gate R4:
- [ ] mejora neta de tiempo total por run.
- [ ] métricas misión al menos iguales al baseline post-P4.2.

Checklist de seguridad (obligatorio por iteración):
- [ ] comparar contra baseline congelado.
- [ ] ejecutar eval multi-seed (`42/43/44`).
- [ ] revisar `true_win_rate`, `loss_rate`, `captured=4/5`, `vp_entry_missed_rate`, `strategy_stuck_ratio`.
- [ ] si hay degradación táctica: revertir optimización y pasar a siguiente hipótesis.

## 🧹 Simplificación de código (sin compat legacy)

Objetivo:
- reducir complejidad y overhead eliminando rutas legacy que ya no aplican al baseline actual.

Principios:
- mantener comportamiento táctico vigente (sin cambios funcionales no intencionales).
- simplificar primero, optimizar después.
- cada simplificación debe tener cobertura de tests + smoke eval.

Paquetes de simplificación:
- [ ] S1 — Observación/encoder:
  - remover compat de shape antiguo y defaults redundantes.
  - consolidar layout canónico del vector en una única referencia.
- [ ] S2 — Evaluación/reporting:
  - unificar cálculo de métricas en una sola ruta (evitar duplicaciones/fallbacks innecesarios).
  - reducir conversiones defensivas repetidas cuando el contrato ya es estable.
- [ ] S3 — OptionExecutor:
  - podar branches históricos/fallbacks no usados.
  - conservar solo guardrails activos y rutas verificadas por tests.
- [ ] S4 — Train lean mode:
  - telemetría mínima en train, completa en eval/debug.
  - flags explícitos para instrumentación pesada.

Gates de simplificación:
- [ ] tests existentes en verde.
- [ ] sin regresión en smoke eval.
- [ ] mejora o mantenimiento de FPS.

## 🗑️ Eliminación de ficheros no usados

Objetivo:
- limpiar deuda técnica de archivos huérfanos/duplicados/obsoletos sin riesgo de romper pipeline.

Proceso obligatorio (4 pasos):
1) Inventario:
   - listar ficheros candidatos (scripts viejos, exports temporales, artefactos duplicados).
2) Verificación de uso:
   - confirmar referencias en código, scripts y docs.
3) Borrado controlado:
   - eliminar en lotes pequeños (no masivo).
4) Validación:
   - tests + comando principal de train/eval smoke.

Checklist de borrado seguro:
- [ ] no borrar modelos/reportes activos del experimento en curso.
- [ ] no borrar archivos de config usados por `run_train_eval.ps1`.
- [ ] documentar cada borrado relevante en bitácora.
- [ ] si hay duda de uso, mover a carpeta `deprecated/` temporal antes de borrar definitivo.

Estado inicial:
- [ ] preparar inventario de candidatos.
- [ ] clasificar por tipo: `legacy_code`, `temp_exports`, `old_reports`, `unused_scripts`.
- [ ] ejecutar primera limpieza controlada post-run.

## 🛠️ Runbook de incidentes (train/eval)

Incidente: mismatch de observación (`(70,) != (74,)`)
- síntoma: `Unexpected observation shape ...`.
- acción: reentrenar modelo y `VecNormalize` con encoder actual.
- verificación: `model_obs_shape == env_obs_shape` antes de eval.

Incidente: `VecNormalize` faltante/incompatible
- síntoma: warning o error al cargar normalizador.
- acción: no reutilizar stats viejas; regenerar en entrenamiento nuevo.
- opción temporal: abortar eval (preferido) en vez de continuar sin normalización.

Incidente: métricas misión en `None` / saturadas
- síntoma: `vp_entry_missed_rate=None` o `=1.000` persistente.
- acción: revisar oportunidades (`vp_entry_opportunities`) y consistencia evaluator/analyzer.
- salida: marcar NO-GO o CONDITIONAL GO según primarios.

Incidente: run detenido o degradación fuerte en train
- síntoma: `approx_kl` fuera de rango, `explained_variance` cae, NaN/inf.
- acción: detener run, conservar logs, volver al último config estable.
- siguiente paso: aplicar una sola corrección (no múltiples cambios simultáneos).

==================================================
## 📝 Bitácora corta

- 2026-06-10 (pre-fix trazabilidad/ownership):
  - `true_win_rate`: ~0.10
  - `loss_rate`: ~0.65-0.67
  - `vp_entry_missed_rate`: 1.000
  - nota: se corrigió instrumentación y distancias de captura locales

- 2026-06-09:
  - pico histórico US ~0.46-0.49 (`100 eps`)
  - posterior regresión por sesgo de compuestas

==================================================
## 🎯 SIGUIENTE PASO

Mientras corre el entrenamiento:
- mantener ajustes actuales (sin meter ruido nuevo)
- ejecutar eval completa `seed 42/43/44` (100 eps cada una, misma snapshot)
- comparar contra baseline congelado y decidir GO/NO-GO
- si NO-GO: aplicar un único ajuste orientado a VP-entry y repetir ciclo corto

Bloqueo conocido resuelto por proceso (no por hotfix):
- `eval_sb3` con modelo viejo falla con:
  - `Could not load VecNormalize stats ... (70,) != (74,)`
  - `Unexpected observation shape (74,) ... expected (70,)`
- acción correcta: reentrenar desde cero con encoder actual y reevaluar.

Trabajo paralelo recomendado (sin contaminar el run):
- cerrar definición final de `vp_entry_missed_rate` y documentar fórmula única
- preparar Fase 2 de observabilidad RL (spec de features + rangos esperados)
- añadir test de regresión de activación multi-bando (Paso 4 de activaciones flexibles)

Checklist rebaseline P4.2:
- [ ] smoke train/eval (`seed 42`, `episodes 30`)
- [ ] run principal (`seed 42/43/44`, `episodes 100`)
- [ ] confirmar gates (`true_win_rate`, `loss_rate`, `captured=4/5`, `vp_entry_missed_rate`, `strategy_stuck_ratio`)
- [ ] si GO: pasar a P4.3 (Action Budget, activación gradual)
