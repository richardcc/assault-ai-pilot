# Roadmap: Curriculum 2 Escenarios + Nuevas Capacidades

## Objetivo

Introducir y estabilizar entrenamiento multi-escenario (`battaglia_cittadina_2_1` + `mettete_i_piedi_terra_1`) sin perder rendimiento VP-first, y después incorporar capacidades de juego nuevas (`vs_past`, humo, refuerzos, minas) con cambios controlados y medibles.

## Revisión del roadmap anterior

Referencia revisada: `docs/CURRICULUM_SELF_VS_RANDOM_ROADMAP.md`.

Qué se mantiene:
- Filosofía de promoción por gates.
- No-regression en métricas críticas.
- Evaluación por bloques y trazabilidad de resultados.

Qué se amplía/corrige para la etapa actual:
- El foco pasa de un solo entorno a **multi-escenario**.
- El pass principal se evalúa por agregado global (selfplay + vs_random), con guardarraíl específico para `vs_random_side_b`.
- Se define orden de adopción de capacidades nuevas para no mezclar variables causales en la misma fase.

## Principios operativos

- Cambiar una variable grande cada vez.
- Mantener baseline promovido antes de introducir nuevas mecánicas.
- Exigir A/B por escenario y por perfil en cada promoción.
- Rollback inmediato si hay colapso en métricas críticas.
- Persistir metadatos de curriculum en BBDD para trazabilidad completa de fases, gates y promociones.

## Trazabilidad en BBDD (nuevo requisito)

Objetivo:
- Poder reconstruir a posteriori qué se ejecutó, con qué mezcla, qué gate pasó/falló y qué decisión de promoción se tomó.

Alcance mínimo (campos a guardar por run/fase/eval):
- `curriculum_name` (ej. `self_vs_self_vs_random_2scenarios_v1`)
- `curriculum_version` (tag/semver/hash de config)
- `phase_name` (ej. `phase1_bootstrap`)
- `phase_index` (orden dentro del curriculum)
- `phase_started_at`, `phase_finished_at`
- `train_run_id` (run id de entrenamiento)
- `eval_run_id` (run id de benchmark/eval)
- `checkpoint_path` (promoted candidate evaluado)
- `scenario_mix_ids` (array de escenarios)
- `scenario_mix_weights` (array de pesos usados)
- `matchup_profiles_enabled` (array perfiles activos)
- `seeds_pack_id` o `seeds_hash` (identidad del pack de seeds)
- `gate_spec_snapshot` (json con thresholds aplicados en esa fase)
- `gate_result_status` (`PASS`/`FAIL`)
- `gate_fail_reasons` (array/string)
- `promotion_decision` (`promote`/`hold`/`rollback`)
- `promotion_reason` (texto corto de decisión)
- `baseline_reference` (run/fase baseline para A/B)

Eventos recomendados:
- `phase_started`
- `phase_completed`
- `gate_evaluated`
- `promotion_decided`
- `rollback_triggered`

Regla operativa:
- Ninguna fase se considera “cerrada” si no existe su registro de BBDD con `gate_spec_snapshot`, `gate_result_status` y `promotion_decision`.

Visibilidad en Web UI (obligatorio):
- Exponer esta trazabilidad en una vista de curriculum/fases dentro del Web UI.
- Mostrar al menos por fase:
  - `curriculum_name`, `curriculum_version`
  - `phase_name`, `phase_index`, timestamps (inicio/fin)
  - mezcla de escenarios (`scenario_mix_ids`, `scenario_mix_weights`)
  - `train_run_id`, `eval_run_id`, `checkpoint_path`
  - estado de gate (`gate_result_status`) y `gate_fail_reasons`
  - decisión (`promotion_decision`, `promotion_reason`)
  - referencia baseline (`baseline_reference`)
- Incluir filtros mínimos:
  - por curriculum
  - por fase
  - por estado de gate (PASS/FAIL)
  - por decisión (promote/hold/rollback)
- Incluir navegación de detalle:
  - click en fase para abrir snapshot de gate (`gate_spec_snapshot`) y resumen A/B.

Criterio de aceptación UI:
- Dado un run de curriculum, se puede reconstruir en UI la línea temporal completa de fases y decisiones sin abrir logs manualmente.

Diseño UI recomendado (hard vs diagnóstico):
- En la vista de detalle de fase, mostrar dos bloques separados:
  - `Gate KPIs (hard)`:
    - `score`
    - `loss_rate` (con no-regression cuando aplique)
    - `xai_vp_capture_take_rate`
    - `tracked_captured_avg`
    - `vp_net_avg_tracked_side`
    - estado del guardarraíl `vs_random_side_b`
  - `Operational KPIs (diagnostic)`:
    - `timeout_rate`
    - `non_timeout_resolution_rate`
    - `resolved_non_timeout_win_rate`
    - tiempos de ejecución (`profile_wall_s`, `episodes_per_second`, etc.)
- Añadir badges visibles:
  - `HARD GATE: PASS/FAIL`
  - `DIAGNOSTIC: WARN/OK` (sin bloquear promoción)
- Regla visual:
  - Solo métricas de `Gate KPIs (hard)` pueden cambiar `promotion_decision`.
  - Métricas diagnósticas nunca deben marcar la fase como FAIL por sí solas.

## Fases recomendadas

### Fase 0 - Baseline 2 escenarios (actual)

Estado esperado:
- Curriculum `self_vs_self_vs_random_2scenarios_v1` configurado y ejecutable.
- Mezcla progresiva definida por **4 pasos de mezcla**:
  1. 80/20
  2. 70/30
  3. 60/40
  4. 50/50 (estable)

Detalle importante:
- “4 pasos” se refiere a la rampa de mezcla de escenarios.
- El curriculum operativo tiene **8 fases**; varias comparten el paso 4 (50/50).

Mapeo exacto (fases -> mezcla):
- `phase1_bootstrap` -> 80/20 (`battaglia_cittadina_2_1` / `mettete_i_piedi_terra_1`)
- `phase1_channel_adapt` -> 70/30
- `phase1_refine_aggressive` -> 60/40
- `phase2_mix_70_30` -> 50/50
- `phase3_mix_50_50` -> 50/50
- `phase4_mix_30_70` -> 50/50
- `phase5_self_dominant_90_10` -> 50/50
- `phase6_self_only_stabilize` -> 50/50

Secuencia operativa de Fase 0:
- Paso A: ejecutar `phase1_bootstrap` y validar gate VP-first.
- Paso B: ejecutar `phase1_channel_adapt` y validar no-regression + VP-first.
- Paso C: ejecutar `phase1_refine_aggressive` y validar delta mínimo VP-first.
- Paso D: ejecutar `phase2` a `phase6` manteniendo 50/50 y endureciendo score en fases tardías.

Gate principal:
- VP-first en fases tempranas.
- Score más exigente en fases tardías.
- Guardarraíl suave en `muzero_vs_random_side_b`.

Criterio de salida de Fase 0:
- Al menos 1 ciclo completo de 8 fases terminado.
- Gates aceptables en agregado global (con excepciones solo justificadas por guardarraíl suave).
- Trazabilidad por escenario visible en resultados (`seed_games` con `scenario_id`).

### Fase 1 - Hardening multi-escenario

Objetivo:
- Confirmar estabilidad real del curriculum de 2 escenarios.

Validaciones mínimas:
- 1-2 ciclos completos.
- A/B contra baseline recovery en ventana equivalente:
  - agregado global,
  - por perfil (`selfplay`, `vs_random_side_a`, `vs_random_side_b`),
  - por escenario (battaglia, mettete).

Salida:
- Baseline promovido “2 escenarios estable”.

### Fase 2 - Incorporar `vs_past` (modelos anteriores)

Objetivo:
- Reducir olvido y explotar menos debilidades del oponente actual.

Regla:
- No introducir en `phase1`.
- Activar desde `phase2`, con rampa de peso baja:
  - inicio: 5-10%
  - intermedio: 10-20%
  - tardío: 15-25% (solo si no hay regresión).

Gate:
- Mejora/estabilidad global + no colapso en `vs_random_side_b`.

### Fase 3 - Capacidad nueva 1: Humo

Objetivo:
- Añadir humo sin introducir otras capacidades simultáneamente.

Validación:
- Smoke run + bloque corto + A/B contra baseline Fase 2.
- No regresión en VP capture rate, score y loss_rate.

### Fase 4 - Capacidad nueva 2: Refuerzos

Objetivo:
- Integrar refuerzos con comportamiento estable.

Validación:
- Misma disciplina de Fase 3.
- Vigilancia reforzada de varianza por seed.

### Fase 5 - Capacidad nueva 3: Minas

Objetivo:
- Integrar minas preservando control de objetivos.

Validación:
- A/B específico de impacto táctico (avance VP, bajas, eficiencia).
- Confirmar no degradación de perfiles más sensibles.

### Fase 6 - Integración final

Objetivo:
- Consolidar en un curriculum integrado:
  - 2 escenarios,
  - `vs_past`,
  - humo + refuerzos + minas.

Salida:
- Candidato de promoción con checklist de rollback.

## Propuesta de reward adicional (finisher controlado)

Objetivo:
- Mejorar la conversión de ventajas tácticas en eliminaciones cuando una unidad enemiga queda cerca de ser destruida.

Decisión:
- Añadir un componente de reward tipo `finisher` de bajo peso.
- Evitar subir agresivamente `kill_weight` global para no desalinear el objetivo VP-first.

Diseño propuesto:
- `finisher_enabled: true`
- `finisher_hp_threshold: 0.20`
- `finisher_window_turns: 2`
- `finisher_bonus: 0.06` a `0.12`
- `finisher_cap_abs: 0.20`

Regla de despliegue:
- Activar primero en fase controlada (`phase3` o `phase4`) con experimento A/B corto.
- Promover solo si mejora resultado global sin dañar métricas VP-first.

Guardrails para aprobar:
- No degradar `xai_vp_capture_take_rate`.
- No degradar `vp_net_avg_tracked_side`.
- No degradar `tracked_captured_avg`.
- Mantener o mejorar `loss_rate` / `win_rate` en agregado y en `vs_random_side_b`.

## Orden lógico + máximo paralelismo

### Regla de dependencias (qué va en serie)

- **Serie obligatoria**:
  1. Baseline 2 escenarios estable.
  2. Hardening multi-escenario (A/B y promoción baseline).
  3. Activación `vs_past`.
  4. Capacidades nuevas (humo, refuerzos, minas), una por vez en producción.
- Motivo: evitar confusión causal en gates y decisiones de promoción.

### Paralelismo permitido (máximo sin romper trazabilidad)

- **Track A (Entrenamiento/Eval, crítico de promoción)**:
  - Ejecuta fases del curriculum en orden y aplica gates.
  - Es la fuente de verdad para `promotion_decision`.

- **Track B (Plataforma de trazabilidad, en paralelo a Track A)**:
  - Implementar persistencia BBDD de metadatos de fase/gate/promoción.
  - Exponer timeline y detalle en Web UI.
  - No bloquea entrenamientos; sí bloquea “cierre formal” de fase en roadmap.

- **Track C (Preparación técnica de capacidades, en paralelo a Track A)**:
  - Preparar humo/refuerzos/minas detrás de flags/config.
  - Añadir tests/telemetría de cada capacidad.
  - No activar en curriculum productivo hasta completar dependencia en serie.

- **Track D (Experimentación controlada, en paralelo a Track A)**:
  - Diseñar y correr A/B corto de `finisher` en rama/entorno aislado.
  - Entregable: recomendación de parámetros para fase posterior.
  - No cambia baseline principal hasta pasar guardrails VP-first.

### Plan operativo por oleadas

- **Oleada 1 (inmediata)**:
  - Track A: cerrar `phase4 -> phase6` del ciclo actual.
  - Track B: esquema BBDD + payload API + vista UI (timeline por fase).
  - Track D: preparar experimento `finisher` (sin activar en mainline).

- **Oleada 2 (tras baseline 2 escenarios estable)**:
  - Track A: introducir `vs_past` desde `phase2` con rampa baja.
  - Track B: dashboards con split hard/diagnostic KPIs.
  - Track C: humo listo detrás de flag.

- **Oleada 3**:
  - Track A: activar humo (A/B corto -> promoción).
  - Track C: refuerzos listos detrás de flag.
  - Track D: calibración fina de `finisher` si pasó guardrails.

- **Oleada 4**:
  - Track A: activar refuerzos (A/B corto -> promoción).
  - Track C: minas listas detrás de flag.

- **Oleada 5**:
  - Track A: activar minas (A/B corto -> promoción).
  - Integración final de todas las capacidades en un ciclo completo.

### Criterio de “máximo paralelismo seguro”

- Se maximiza paralelismo en ingeniería (BBDD/UI/flags/tests/experimentos),
- pero se mantiene **una sola línea de promoción** en entrenamiento para preservar trazabilidad y decisiones claras de gate.

## Baseline oficial (congelado)

Se fija como baseline de trabajo para este roadmap la última ejecución completa de:
- `curriculums/self_vs_self_vs_random_recovery_v1/run_all_phases.ps1`

Resultado de referencia:
- Ejecución completa con `7 gate failure(s)` y degradación progresiva desde `phase3`.
- Patrón observado:
  - `phase1/phase2`: fallos cercanos a umbral (margen pequeño).
  - `phase3+`: caída en `score`, `xai_vp_capture_take_rate`, `tracked_captured_avg`, `vp_net_avg_tracked_side`.

Regla de uso del baseline:
- Este baseline se usa como punto de comparación fijo para iteraciones del roadmap.
- No se considera baseline “promovible” para fases tardías (`phase5/phase6`), pero sí baseline operativo para medir mejora incremental.

## Articulación de mejora incremental

Objetivo:
- Mejorar de forma controlada sin mezclar demasiadas variables por ciclo.

Ciclo corto recomendado (iterativo):
1. Seleccionar una sola palanca de cambio (gates, mezcla, reward finisher o `vs_past`).
2. Ejecutar tramo acotado (`phase3 -> phase4` o `phase3 -> phase5`) con `-StopOnGateFail`.
3. Comparar contra este baseline en:
   - agregado global,
   - `vs_random_side_b` (perfil crítico),
   - VP-first (`vp_capture_take_rate`, `tracked_captured_avg`, `vp_net_avg_tracked_side`).
4. Promover cambio solo si mejora clara en VP-first sin regresión severa en `loss_rate`.
5. Registrar decisión en BBDD/UI (PASS/HOLD/ROLLBACK) antes de iniciar siguiente iteración.

Priorización inicial de palancas (orden sugerido):
- P1: recalibración suave de umbrales de fase tardía para evitar falsos negativos de progreso real.
- P2: experimento controlado de `finisher` (A/B corto) en `phase3/phase4`.
- P3: introducir `vs_past` desde `phase2` con peso bajo (5-10%).

Definición de éxito para la siguiente iteración:
- Reducir fallos en fases tardías (objetivo: <= 3 fases con fallo),
- y mejorar `vs_random_side_b` frente al baseline congelado.

## Snapshot de métricas actuales (baseline de tracking)

Fuente:
- salida final de `curriculums/self_vs_self_vs_random_recovery_v1/run_all_phases.ps1`
- estado: `Curriculum completed with 7 gate failure(s)`

Valores por fase (baseline):

- `phase1_bootstrap`
  - `tracked_captured_avg`: **2.34444444444444** (umbral 2.35)

- `phase1_channel_adapt`
  - `tracked_captured_avg`: **2.36111111111111** (umbral 2.40)

- `phase2_mix_70_30`
  - `tracked_captured_avg`: **2.41666666666667** (umbral 2.45)

- `phase3_mix_50_50`
  - `score`: **0.577777777777778** (umbral 0.60)
  - `xai_vp_capture_take_rate`: **0.0664563250302354** (umbral 0.07)
  - `tracked_captured_avg`: **2.41111111111111** (umbral 2.48)

- `phase4_mix_30_70`
  - `score`: **0.511111111111111** (umbral 0.62)
  - `xai_vp_capture_take_rate`: **0.0735779321596054** (umbral 0.08)

- `phase5_self_dominant_90_10`
  - `score`: **0.561111111111111** (umbral 0.64)
  - `xai_vp_capture_take_rate`: **0.0652974913067754** (umbral 0.095)
  - `tracked_captured_avg`: **2.35555555555556** (umbral 2.52)
  - `vp_net_avg_tracked_side`: **0.355555555555556** (umbral 0.47)

- `phase6_self_only_stabilize`
  - `score`: **0.577777777777778** (umbral 0.66)
  - `xai_vp_capture_take_rate`: **0.0683625303911811** (umbral 0.105)
  - `tracked_captured_avg`: **2.32777777777778** (umbral 2.55)
  - `vp_net_avg_tracked_side`: **0.327777777777778** (umbral 0.50)

Regla de tracking para próximas iteraciones:
- Registrar para cada fase:
  - valor baseline,
  - valor nuevo,
  - delta absoluto y delta porcentual,
  - estado (`improve`, `flat`, `regress`).
- Considerar mejora real cuando:
  - suben métricas VP-first en `phase3+`,
  - y no hay regresión severa en `loss_rate` / perfil crítico `vs_random_side_b`.

## Iteration 1 pack (arranque rápido)

Objetivo:
- Ejecutar validación de mejora en `phase3/phase4` con corte temprano y coste acotado.

Artefactos preparados:
- Curriculum iteración:
  - `curriculums/self_vs_self_vs_random_recovery_v1/curriculum.iter1_phase34.yaml`
  - Ajusta solo gates de `phase3/phase4` para detectar mejora direccional.
- Script de comparación:
  - `scripts/compare_curriculum_eval_logs.py`
  - Compara `02_eval.log` baseline vs candidato para `win_rate`, `avg_return`, `timeout_rate`, `avg_steps`.

Comando de ejecución recomendado (rápido, sin quemar horas):
- `powershell -ExecutionPolicy Bypass -File ".\curriculums\self_vs_self_vs_random_recovery_v1\run_all_phases.ps1" -CurriculumYaml ".\curriculums\self_vs_self_vs_random_recovery_v1\curriculum.iter1_phase34.yaml" -StartPhase phase3_mix_50_50 -StopOnGateFail`

Comando de comparación (al terminar eval de phase3/phase4):
- `.\.venv\Scripts\python.exe .\scripts\compare_curriculum_eval_logs.py --baseline "<baseline 02_eval.log>" --candidate "<candidate 02_eval.log>"`

Decisión operativa:
- Si `phase3` mejora VP-first y no empeora severamente `vs_random_side_b`, continuar a `phase4`.
- Si `phase3` falla con regresión clara, HOLD/ROLLBACK y no ejecutar `phase5/phase6`.

## Gates y rollback (plantilla)

Gates mínimos por fase:
- No-regression en `loss_rate` donde aplique.
- VP metrics (`xai_vp_capture_take_rate`, `tracked_captured_avg`, `vp_net_avg_tracked_side`) dentro de umbral.
- Score dentro de límites de fase.
- Guardarraíl `vs_random_side_b`:
  - permitir promoción con mejora global,
  - bloquear si hay caída severa (floor o drop máximo configurable).

Nota sobre tiempo/timeout:
- `timeout_rate` y métricas derivadas de no-timeout se tratan como diagnóstico operativo.
- No deben actuar como hard gate de promoción en este juego, donde muchas partidas se resuelven por consumo de turnos.

Rollback inmediato si:
- Spike severo de derrota vs baseline promovido.
- Colapso de métricas VP en 2 bloques consecutivos.
- Empeoramiento sostenido en perfil crítico (`vs_random_side_b`).

## Checklist de ejecución

- [ ] Baseline 2 escenarios estable y documentado.
- [ ] A/B por escenario y perfil publicado.
- [ ] `vs_past` activado desde `phase2` con rampa.
- [ ] Humo integrado y validado.
- [ ] Refuerzos integrados y validados.
- [ ] Minas integradas y validadas.
- [ ] Integración final con plan de rollback.
- [ ] Trazabilidad en BBDD activa (campos de curriculum/fase/gate/promoción persistidos).
- [ ] Trazabilidad visible en Web UI (timeline por fase + estado de gates + decisión de promoción).
