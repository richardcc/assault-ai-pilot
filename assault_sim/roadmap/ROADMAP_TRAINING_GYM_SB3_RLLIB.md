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
## 📅 FASE P0 — US Objetivos (ACTIVA 🔥)

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
## ✅ ESTADO ACTUAL (snapshot)

Ya tienes:
- motor táctico completo
- pipeline SB3 estable
- selección de unidad por policy
- fix anti-ping-pong
- trazas fiables (sampled/resolved/executed + distancias locales)

Falta para cerrar P0:
- consolidar mejora multi-seed estable
- corregir/ajustar métrica de entrada VP
- reducir dependencia de decisiones forzadas sin perder resultados

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

Trabajo paralelo recomendado (sin contaminar el run):
- cerrar definición final de `vp_entry_missed_rate` y documentar fórmula única
- preparar Fase 2 de observabilidad RL (spec de features + rangos esperados)
- añadir test de regresión de activación multi-bando (Paso 4 de activaciones flexibles)
