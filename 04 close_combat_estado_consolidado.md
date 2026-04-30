# ✅ Estado Consolidado del Proyecto – Close Combat / Assault

Este documento **deja el estado del sistema preparado** para continuar en otro chat sin pérdida de contexto.  
Es la **fuente de verdad actual** para el sistema de **Asalto / Close Combat**.

---

## ✅ Estado actual (confirmado y estable)

### 🧠 Arquitectura

- **Acciones declarativas**  
  `AssaultAction(unit_id, target_id)` **no contiene lógica**.

- **Resolver central**  
  Toda la lógica del asalto vive en `close_combat_resolver.py`.

- **Separación estricta de responsabilidades**:
  - `GameState`: datos pasivos.
  - `RuntimeGameState`: reglas (resolución, eliminación).
  - `SimEnv`: control del episodio (**END‑MATCH + ganador**).
  - `ConsoleObserver`: **toda la presentación** (sin `print()` en el motor).

---

## 🛑 Fin de partida (END‑MATCH)

- **Guard clause temprano en `SimEnv.step()`**  
  - Si `active_unit is None` → **END‑MATCH inmediato**.

- **Último bando en pie**  
  - Si queda **un solo `side` vivo** →  
    ✅ ganador declarado  
    ✅ evento `MATCH_END` emitido

- ✅ **Sin bucles** (`UNKNOWN -> None` eliminado definitivamente).

---

## 🗡️ Combate

- **Resolución simultánea por rondas**
- **MUTUAL_DESTRUCTION** soportado
- **Eliminación** ocurre **solo tras** `CLOSE_COMBAT_END`
- **Trazabilidad por ronda garantizada**

---

## 🎨 Observabilidad

- ❌ El motor **no imprime**
- ✅ Todo se ve vía **eventos**
- ✅ `ConsoleObserver` controla toda la salida
- ✅ **Banner final** con ganador (🏆) y razón

---

## 📦 Componentes implicados (actuales)

```text
assault_model/
├─ actions/
│  └─ assault.py                 # AssaultAction (declarativa)
├─ combat/
│  ├─ combat_action_context.py   # Contexto del asalto
│  ├─ combat_resolution.py       # Resultados semánticos
│  └─ close_combat_resolver.py   # Lógica completa del Close Combat
├─ map/
│  └─ combat_geometry.py         # determine_attack_sector