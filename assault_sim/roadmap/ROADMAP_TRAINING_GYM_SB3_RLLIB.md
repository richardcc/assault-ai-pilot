# ROADMAP Training 2026 (Operativo)

## Estado actual (2026-06-09)

Objetivo activo:
- consolidar US en escenarios de objetivos (captura VP) y pasar de estabilidad a mejora incremental de victoria real.

Estado observado:
- pipeline oficial: `GymAssaultEnv + SB3 PPO`;
- `true_win_rate` US subio de ~0.00 a ~0.46-0.49 (100 episodios) en `battaglia_cittadina_2_1`;
- aun hay margen: `draw_rate` y `strategy_stuck_ratio` siguen altos.

Cambios clave ya implementados:
- [x] accion RL de 4 componentes: `[strategy, option, attack_mode, unit_slot]`;
- [x] seleccion de unidad por policy integrada al scheduler;
- [x] fix critico de distancia (`safe_hex_distance` admite `HexCoord` y `(q, r)`);
- [x] anti-loop de `objective_staging_move` reforzado;
- [x] rol atacante/defensor explicitado via `victory_outcomes.tracked_side`.

---

## Decisiones vigentes

- mantener SB3 como ruta principal;
- no introducir L4 por ahora;
- priorizar ajustes de decision/reward sobre cambios arquitectonicos grandes;
- usar `tracked_side` del escenario como fuente de verdad del rol atacante/defensor.

---

## Prioridad P0 (US Objetivos)

Meta:
- estabilizar `true_win_rate >= 0.50` multi-seed sin degradar control de VP.

Pendientes:
- [ ] bajar `draw_rate` sin subir `loss_rate`;
- [ ] reducir `strategy_stuck_ratio`;
- [ ] mejorar conversion `captured=3 -> captured=4/5`;
- [ ] revisar/coherenciar `vp_entry_missed_rate` (actualmente inconsistente con wins observados).
- [ ] consolidar baseline sin degradacion antes de activar reglas nuevas (`reaction_fire`).

Guardrails:
- [ ] evitar loops de `RETREAT` fuera de emergencia;
- [ ] evitar oscilacion posicional A->B->A;
- [ ] mantener excepciones de emergencia (hp/suppression/amenaza cercana).

Plan de recuperacion baseline (3 iteraciones cortas):
- [ ] Iteracion 1: reducir sesgo `PRESERVE/RETREAT`, priorizar `ATTACK` util cuando exista tiro legal.
- [ ] Iteracion 2: recalibrar scoring de compuestas (`move/fire`) para mantener uso >0 sin hundir `damage_ratio`.
- [ ] Iteracion 3: cerrar con eval multi-seed (42/43/44, 100 eps) y fijar nuevo baseline minimo.

---

## Metricas de referencia

Primarias:
- `true_win_rate`
- `tracked_result_counts`
- `captured_final_counts`
- `avg_vp`

Secundarias:
- `draw_rate`, `loss_rate`
- `strategy_stuck_ratio`
- `attack_opportunity_cost_near_vp`
- `capture_attempt_success_rate`
- `unit_concentration_index`
- `multi_unit_contribution`

---

## Gating operativo (iteraciones cortas)

GO:
- `true_win_rate` sube o se mantiene >= baseline reciente;
- `loss_rate` no empeora de forma material;
- `captured_final_counts` mantiene masa en `4/5`.

NO-GO:
- cae `true_win_rate` de forma consistente;
- sube `loss_rate` de forma sostenida;
- vuelve saturacion en `captured=3`.

Regla:
- preferir ciclos cortos de train+eval con trazas (`record_sb3_trace`) antes de tunings largos.

---

## P2 RLlib (background)

Pendiente:
- [ ] cerrar runner de evaluacion totalmente agnostico;
- [ ] validar checklist RLlib-ready end-to-end;
- [ ] documentar decision final SB3-only vs RLlib activo.

Nota:
- no bloquear P0 por trabajo de framework.

---

## Backlog Reglas Tacticas (Reglamento 8.2 / 8.4 / 9.3)

Objetivo:
- alinear simulacion con reglas de reaccion y movimiento+fuego para mejorar realismo tactico y evitar rutas de captura "gratis".

Secuencia aprobada (2026-06-09):
- [x] decision: implementar primero `move_and_fire` / `fire_and_move` en MVP controlado.
- [ ] mantener `reaction_fire` desactivado temporalmente hasta recuperar baseline (`true_win_rate` y `damage_ratio`).

MVP inmediato (siguiente iteracion):
- [ ] `move_then_fire`: mover hasta mitad de MA (ceil) y luego disparar.
- [ ] `fire_then_move`: disparar y luego mover hasta mitad de MA (ceil).
- [ ] restriccion: artilleria no puede usar acciones compuestas de move/fire.
- [ ] aplicar bonus defensivo al defensor durante `move/fire`.
- [ ] no marcar spotted automatico en `fire_then_move` (segun regla).
- [ ] evaluacion A/B contra baseline estable actual antes de activar reaction fire.

MVP `reaction_fire` (postergado):
- [ ] `reaction_fire` en `Action Phase` (no en `Support Phase`).
- [ ] trigger inicial: `MoveAction` (normal/fast) del bando activo.
- [ ] una sola unidad reactora por lado y turno (si no fue activada).
- [ ] validacion LOS/rango y bloqueo en entrada a hex de close combat.
- [ ] resolver reaccion usando pipeline de `Ranged Fire` existente.

Fase 2:
- [ ] ampliar triggers: `move&fire`, `fire&move`, `fallback`, `detachment`, `emergency disembark`.
- [ ] reaccion por hex entrado (no solo por accion completa).
- [ ] marcar estado de unidad que dispara en reaccion.

Fase 3:
- [ ] acciones compuestas `move_then_fire` y `fire_then_move` (hasta media MA, redondeo arriba).
- [ ] prohibir `move/fire` a artilleria.
- [ ] aplicar bonus defensivo al defensor en `move/fire`.
- [ ] no auto-spot al hacer `fire&move`, segun regla.

Impacto esperado en RL:
- [ ] observacion: riesgo de reaccion por ruta/hex.
- [ ] reward: penalizar movimientos que exponen reaccion desfavorable.
- [ ] reevaluar gates de captura tras activar reglas.

---

## P3 Escalado (post-P0 estable)

Activar cuando P0 esté estable:
- [ ] profiling hotspots simulador;
- [ ] curriculum de complejidad (mapa/unidades/horizonte);
- [ ] tuning throughput/paralelismo;
- [ ] SLO 24h + eval multi-seed.

---

## Ultimos resultados (bitacora corta)

- 2026-06-09:
  - `true_win_rate(US, battaglia_cittadina_2_1, 100eps)`: 0.49
  - `draw_rate`: 0.31
  - `loss_rate`: 0.20
  - `captured_final_counts`: `5:23, 4:26, 3:31, 2:14, 1:6`
  - Nota: fix de distancia + seleccion de unidad por policy desbloquearon captura real; siguiente foco es bajar draws.

- 2026-06-09 (seed=44, eval 100eps):
  - `true_win_rate`: 0.12 -> 0.03 (regresion tras sesgo de compuestas)
  - `damage_ratio`: 0.515 -> 0.016 (colapso ofensivo RL)
  - `composite_usage`: `available_actions=40342, selected=156, select_rate_when_available=0.076`
  - Decision operativa: mantener `reaction_fire` OFF; priorizar recuperacion de baseline con `move/fire` conservador.


