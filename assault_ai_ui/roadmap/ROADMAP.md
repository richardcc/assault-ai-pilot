# ASSAULT AI UI — ROADMAP OPERATIVO (LIMPIO)

## Ultima actualizacion (2026-06-27)

## Objetivo

Entregar una experiencia estable de juego humano vs IA con:

- loop de partida robusto
- UX clara para decisiones humanas
- explainability integrada
- base lista para replay

## Alineacion de arquitectura

Backend de juego vigente:

- `POST /api/game/start`
- `GET /api/game/state`
- `POST /api/game/step`
- `POST /api/game/actions`
- `POST /api/game/ai-turn`
- `POST /api/explain/activation`
- `GET /api/game/trace`

## Componentes funcionales (separados)

1. **Reglas de juego (core tactico)**
   - fuente de verdad del estado, legalidad de acciones y resolucion de combate
   - vive en el motor/simulador y sus endpoints de juego

2. **RAG (copiloto del sistema)**
   - componente oficial para consulta, explicaciones ampliadas y soporte de decision
   - se mantiene desacoplado del loop tactico critico de turno

Nota:

- no usar `/api/game/next` (obsoleto)
- no mezclar llamadas de RAG dentro del loop critico de `step/ai-turn`

## Estado actual

Hecho:

- [x] render hex + unidades + escenarios desde backend
- [x] base de control por bandos (backend decide turno)
- [x] endpoint de explainability de activacion

En curso:

- [~] endurecer flujo UI de turno humano vs turno IA (evitar overrides manuales)
- [~] pulir feedback de acciones invalidas y estados de espera

Pendiente:

- [ ] replay viewer de producto (timeline + play/pause)
- [ ] polish visual (animaciones, overlays, calidad de interaccion)

## Prioridades inmediatas (ordenadas)

1. **Integridad del loop de partida UI-backend**
   - bloquear acciones manuales fuera de turno humano
   - sincronizar siempre con `state` post-step y post-ai-turn
   - garantizar que UI no intente decidir el orden de activacion

2. **Explainability usable en UI**
   - mostrar `strategic_intent` y `tactical_execution` por activacion
   - fallback visual cuando no haya eventos tacticos

3. **Integracion RAG sin acoplar turnos**
   - habilitar panel de copiloto RAG separado de la logica de turno
   - usar RAG como apoyo de interpretacion, no como autoridad de reglas

4. **Observabilidad de partida**
   - integrar consumo de `GET /api/game/trace`
   - panel de depuracion minimo para soporte de QA

## Criterio de cierre de sprint UI

- partida completa humano vs IA sin bloqueos de turno
- cero llamadas a endpoints obsoletos (`/api/game/next`)
- explainability visible y consistente en activaciones clave

==================================================