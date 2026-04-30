# 🧭 Plan de Reconstrucción del Combate de Asalto (Close Combat)

Este documento consolida **la decisión estratégica y técnica** alcanzada tras un análisis completo del código antiguo, del manual de reglas y del motor actual. Es la **fuente de verdad** para implementar nuevamente el **Close Combat / Assault** usando el **nuevo patrón arquitectónico**, reutilizando y depurando la **lógica antigua**.

---

## ✅ Decisión clave

> **El asalto se reimplementa completamente** usando el **nuevo patrón (acción declarativa + resolver central)**, **reaprovechando fielmente la lógica antigua**, para poder **validar su corrección respecto al manual**.

No se mantiene compatibilidad legacy directa, pero **sí equivalencia lógica**.

---

## 📁 Arquitectura final implicada

```text
assault_model/
├─ actions/
│  └─ assault.py          # AssaultAction (declarativa)
├─ combat/
│  ├─ combat_action_context.py
│  ├─ combat_resolution.py
│  └─ close_combat_resolver.py
├─ map/
│  └─ combat_geometry.py  # sector de ataque
```

**Principios no negociables**:
- `AssaultAction` **no contiene lógica**
- `ActionCatalog` **no construye perfiles**
- **Toda la lógica del asalto vive en el resolver**

---

## 🧠 Modelo conceptual correcto del Asalto

### 🔹 Sectores de ataque

```python
AttackSector = { FRONT, FLANK_LEFT, FLANK_RIGHT, REAR }
```

Nunca se usa un `FLANK` genérico. Los modificadores se aplican **a partir del sector**, no al revés.

---

### 🔹 Secuencia de Close Combat (por round)

1. Determinar sector
2. Construir pools de ataque y defensa (ambos bandos)
3. Tirada **simultánea**
4. Cancelaciones
5. Aplicación de efectos simultánea
6. Comprobar eliminación / retirada
7. Si ambos sobreviven → siguiente round

---

## 🧩 Nuevos componentes

### 1️⃣ AssaultAction

```python
AssaultAction(unit_id, target_id)
```

Acción puramente declarativa.

### 2️⃣ CombatActionContext

Contiene:
- attacker / defender
- posiciones
- attack_sector
- round_number
- flags (adrenaline_rush, first_round)

### 3️⃣ resolve_close_combat(ctx)

Resolver dedicado, equivalente funcional a la lógica antigua.

---

## 🧪 Depuración y validación

El resolver devuelve:
- CombatResolutionResult
  - round_reports[]
  - final_outcome
  - new_game_state

Cada round debe ser trazable y compararse con:
- manual
- versión antigua

---

## ✅ Qué NO se hace

- ❌ No lógica de combate en heurística
- ❌ No ActionCatalog complejo
- ❌ No perfiles hardcoded en acciones

---

## 🎯 Objetivo final

- Asalto fiel al manual
- Implementación limpia y moderna
- Comparación round-a-round
- Base sólida para IA y RL

---

## 🔜 Próximo paso técnico

1️⃣ Implementar `determine_attack_sector()`
2️⃣ Implementar el esqueleto de `resolve_close_combat(ctx)`
3️⃣ Reinyectar lógica antigua (dados, cancelaciones, críticos)

Este documento sustituye cualquier plan previo de asalto.
