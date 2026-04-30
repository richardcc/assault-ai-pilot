# 🗡️ Close Combat / Assault – Estado Consolidado

Este repositorio contiene la **reimplementación moderna del sistema de Asalto (Close Combat)**, fiel al manual original y diseñada para ser **trazable, testeable y compatible con IA / RL**.

Este documento es la **fuente de verdad** del estado actual del sistema.

---

## ✅ Estado actual

El sistema se encuentra en un **estado estable y coherente**, con:

- ✅ Arquitectura limpia (acciones declarativas + resolver central)
- ✅ Combate simultáneo por rondas
- ✅ Eliminación correcta de unidades
- ✅ Fin de partida robusto (END‑MATCH)
- ✅ Ganador declarado automáticamente
- ✅ Observabilidad desacoplada (solo eventos)
- ✅ Sin bucles ni estados zombis

---

## 🧠 Arquitectura

### Principios clave

- **Las acciones NO contienen lógica**
- **Toda la lógica del asalto vive en el resolver**
- **El motor no imprime nada**
- **La presentación se hace exclusivamente vía observers**

### Separación de responsabilidades

| Componente | Responsabilidad |
|-----------|-----------------|
| `GameState` | Datos pasivos |
| `RuntimeGameState` | Reglas (resolución, eliminación) |
| `SimEnv` | Control del episodio (END‑MATCH + ganador) |
| `ConsoleObserver` | Presentación y formato |

---

## 🗡️ Modelo del Asalto (Close Combat)

### Sectores de ataque

```python
AttackSector = { FRONT, FLANK_LEFT, FLANK_RIGHT, REAR }
```

- ❌ Nunca se usa `FLANK` genérico
- ✅ Los modificadores **derivan del sector**

---

### Secuencia por ronda

1. Determinar sector de ataque
2. Construir pools de ataque y defensa (ambos bandos)
3. Tirada **simultánea**
4. Cancelaciones
5. Aplicación **simultánea** de efectos
6. Comprobar eliminación
7. Repetir si ambos sobreviven

---

## 💥 Combate

- Resolución **simultánea**
- Soporte explícito de **MUTUAL_DESTRUCTION**
- Eliminación **solo tras `CLOSE_COMBAT_END`**
- Cada ronda es **trazable y comparable con el manual**

---

## 🛑 Fin de partida (END‑MATCH)

El partido termina cuando se cumple **una** de estas condiciones:

1. **No hay unidad activa**
2. **Solo queda un bando vivo**

En ese caso:
- ✅ Se declara ganador
- ✅ Se emite `MATCH_END`
- ✅ El episodio se detiene inmediatamente

---

## 🎨 Observabilidad

- ❌ El motor **no usa `print()`**
- ✅ Todo se comunica mediante **eventos**
- ✅ `ConsoleObserver` controla toda la salida
- ✅ Banner final con ganador (🏆)

---

## 📦 Estructura relevante

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
```

---

## 🚫 Decisiones explícitas (NO hacer)

- ❌ Lógica de combate en heurísticas
- ❌ `ActionCatalog` con perfiles
- ❌ Prints en el motor
- ❌ Compatibilidad legacy directa  
  ✅ **Sí equivalencia lógica**

---

## 🎯 Objetivo final

- Asalto **fiel al manual**
- Implementación **limpia y moderna**
- Comparación **round‑a‑round** con la versión antigua
- Base sólida para **IA / Reinforcement Learning**

---

## ▶️ Próximos pasos técnicos

1. ✅ Validar `determine_attack_sector()`
2. ✅ Finalizar `resolve_close_combat(ctx)`
3. 🔜 Reinyectar lógica antigua:
   - dados
   - cancelaciones
   - críticos
4. 🔜 Validación cruzada con el manual
5. 🔜 Tests deterministas por seed

---

> Este README sustituye cualquier documentación previa sobre el asalto.
> Listo para continuar el desarrollo con seguridad.
