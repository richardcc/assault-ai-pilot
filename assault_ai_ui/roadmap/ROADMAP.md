🚀 ASSAULT AI UI — ROADMAP COMPLETO

==================================================
🧭 VISIÓN
==================================================

Construir un sistema completo:

- 🎮 Jugar vs AI (IA vs jugador humano)
- 🔁 Visualizar replays
- 🧠 Explainability (HRL + decisiones)
- 🤖 RAG Assistant flotante

IMPORTANTE:
El sistema es por BANDOS, no por número de unidades.
Alternancia: GE → US → GE → US…
Si un bando se queda sin unidades activables, el otro sigue.

==================================================
🧱 ARQUITECTURA FINAL
==================================================

BACKEND:
- SimEnv (motor del juego)
- ActivationManager (controla turnos)
- HRLController (IA entrenada)
- OptionExecutor (convierte decisiones en acciones)
- FastAPI

Endpoints:

- POST /api/game/start
- GET  /api/game/next
- POST /api/game/step
- GET  /api/game/state
- POST /api/explain
- POST /api/rag/query

FRONTEND:
- React + TypeScript + Vite
- PixiJS (mapa)
- UI React (paneles, botones)

==================================================
📌 MODELO DE TURNO (CRÍTICO)
==================================================

NO es por unidad emparejada.

ES así:

Turno:
  GE → activa 1 unidad
  US → activa 1 unidad
  GE → siguiente unidad disponible
  US → siguiente unidad disponible

Si un bando no tiene unidades activables:
  → se salta
  → el otro bando continúa

La UI NO decide el orden.
El orden SIEMPRE lo decide el backend (ActivationManager).

==================================================
📅 FASE 0 — ENTORNO ✅
==================================================

- Vite funcionando
- React + TypeScript
- npm run dev

==================================================
📅 FASE 1 — RENDER DEL MAPA ✅
==================================================

- Grid hexagonal
- Hover
- Selección de hex
- Colores por terreno (modo debug)
- Texto legible (shadow + resolution fix)
- Render estable Pixi v8

==================================================
📅 FASE 2 — ESCENARIO BACKEND → UI ✅
==================================================

Endpoint:
GET /api/ui/scenarios/{id}

Devuelve:
- shape del mapa
- hexes (q, r, terrain)
- units (q, r, side)

UI ya renderiza:
- grid
- terreno
- unidades (posición base)

==================================================
📅 FASE 3 — LOOP DE JUEGO (CRÍTICO 🔥)
==================================================

OBJETIVO:
Conectar UI ↔ SimEnv

Flujo:

1. UI → /game/start
2. backend crea:
   - SimEnv
   - ActivationManager
   - HRLController

3. UI pide:
   GET /game/next

4. backend responde:
{
  unit_id,
  side,
  position
}

5. UI:

   if side == IA:
       autoplay (backend decide)
   else:
       esperar input usuario

6. Usuario hace acción:
   → click / botón

7. UI → POST /game/step

8. backend:
   → SimEnv.step(action)
   → actualiza GameState

9. UI renderiza nuevo estado

Loop se repite

==================================================
📅 FASE 4 — CONTROL HUMANO
==================================================

Para unidades del jugador:

- Selección de unidad
- Click en hex destino
- Acciones disponibles:
  - MOVE
  - ATTACK
  - WAIT

UI debe preguntar:

GET /game/actions?unit_id=XXX

backend responde:
- lista de acciones válidas

==================================================
📅 FASE 5 — AUTOPLAY IA
==================================================

Para IA:

- backend usa HRLController
- decide:
  - option (ATTACK / ADVANCE / etc)
- OptionExecutor convierte → acción real
- backend ejecuta step automáticamente

UI solo renderiza

==================================================
📅 FASE 6 — EXPLAINABILITY 🧠
==================================================

Endpoint:
POST /api/explain/activation

Devuelve:
- strategic_intent (HRL)
- tactical_execution (rules + dice)

UI:
- panel lateral
- tooltip en hover
- explicación por acción

==================================================
📅 FASE 7 — REPLAYS
==================================================

Backend:
- guarda eventos (event_bus)

Formato:
- lista de eventos:
  - MOVE
  - ATTACK
  - DAMAGE
  - HRL_DECISION

UI:
- play / pause
- timeline
- scrubbing turno a turno

==================================================
📅 FASE 8 — RAG ASSISTANT 🤖
==================================================

Endpoint:
POST /api/rag/query

UI:
- chat flotante

Ejemplos:
- "¿Por qué atacó aquí?"
- "¿Qué opción era mejor?"

Backend responde usando:
- HRL + reglas

==================================================
📅 FASE 9 — UI PRO
==================================================

- ocultar coords en modo normal
- iconos terreno
- animaciones:
  - movimiento
  - disparo
  - impacto
- selección visual de unidades
- overlay de rangos

==================================================
📅 FASE 10 — GAME READY 🚀
==================================================

- IA vs humano
- múltiples escenarios
- guardado de partida
- replay viewer
- explicación integrada

==================================================
✅ ESTADO ACTUAL
==================================================

Ya tienes:

✔ motor de juego completo
✔ IA entrenada (PPO + HRL)
✔ render hex grid
✔ backend con escenarios
✔ explainable engine

FALTA SOLO:

🔥 conectar loop de juego en tiempo real

==================================================
🎯 SIGUIENTE PASO
==================================================

Implementar:

👉 /api/game/start
👉 /api/game/next
👉 /api/game/step

Y conectar con UI

==================================================