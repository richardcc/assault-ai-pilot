# Línea 4: Explicabilidad Máxima (XAI), Perfilado Causal e Inteligencia Táctica (IPB)

> **Documento Modular de la Hoja de Ruta Evolutiva**  
> **Importancia Global:** 🟢 **Prioridad P1 (Alta)**  
> **Objetivo Estratégico:** Proporcionar transparencia total sobre las decisiones de la IA conforme a la Sección 13 de las Premisas del Proyecto. Auditar por qué el agente ataca, defiende o se repliega, detectando chokepoints topográficos y correlacionando el plan macro con el desenlace del combate.  
> **Ámbito de Implementación:** `mlops/reporting/explainability_api.py` • `mlops/reporting/causal_profiler.py` • `assault_ai_ui/src/` • `agents/efficientzero_v2/core/macro_planner.py` • `assault_model/units/`

---

## 1. Diagrama de Dependencias y Flujo de Trabajo

```mermaid
flowchart TD
    T4_1["4.1 Atribución Causal Espacial: IGNH / GradCAM Hexagonal (P1)"] --> T4_2["4.2 Perfilador Causal de Partidas y SitRep Forense (P1)"]
    T4_2 --> T4_3["4.3 Perfilado 5D de Unidades y Detección Automática de Chokepoints (P2)"]
    T4_2 --> T4_4["4.4 Perfilado Doctrinal Dinámico y Visibilidad MLOps (P1)"]
```

---

## 2. Matriz de Tareas y Criterios Cuantitativos de Aceptación

| Orden | Tarea / Componente | Prioridad Interna | Módulos / Archivos Impactados | Criterio de Aceptación Cuantitativo | Prerrequisitos |
| :---: | :--- | :---: | :--- | :--- | :--- |
| **1** | **4.1 Atribución Causal Espacial Hexagonal (IGNH / GradCAM)** | **P1** | `mlops/reporting/explainability_api.py`, `assault_ai_ui/src/components/ExplainabilityModal.tsx` | Visualización en el visor MLOps de qué canales sensoriales (cobertura, LOS, amenaza, distancia a VP) determinaron la acción seleccionada en cada turno mediante Integrated Gradients para características heterogéneas (IGNH). | Línea 1 (Zero-Mock en UI) |
| **2** | **4.2 Perfilador Causal de Partidas y SitRep Forense** | **P1** | `mlops/reporting/causal_profiler.py`, `assault_rag/` | Correlación causal automática entre las predicciones tácticas de las cabezas (`threat_map`, `morale_pred`, `objective_intent`) y el resultado de las capturas de VPs. Generación de informe narrativo forense por partida. | Tarea 4.1 |
| **3** | **4.3 Perfilado 5D de Unidades y Detección Automática de Chokepoints (IPB)** | **P2** | `assault_model/map/topography_analyzer.py`, `agents/efficientzero_v2/core/macro_planner.py` | Análisis topográfico previo a la partida (Turno 0) que clasifica hexágonos en *Defilade Corridors*, *Killzones* y *Key Terrain* (VPs), inyectando estos priors en el `MacroStrategyPlanner`. | Tarea 4.2 |
| **4** | **4.4 Perfilado Doctrinal Dinámico de Unidades y Visibilidad en MLOps** | **P1** | `assets/catalogs/unit_catalog.json`, `assault_model/units/unit_type.py`, `agents/efficientzero_v2/core/macro_planner.py`, `mlops/reporting/viewer_frontend/` | Jerarquía 3 capas (Balística, Roles, Emergente). Mutación dinámica contextual de roles (`SPEARHEAD`, `FIRE_SUPPORT`, `RECON`, `SCREEN`, `COMMAND`), modulación +35% de priors MCTS y badges visuales con telemetría forense de rol en Match Replay (:8778). | Tarea 4.2 / Línea 2 |

---

## 3. Estado de Ejecución y Logros Técnicos

> [!NOTE] POSIBLE CONTENIDO REPETIDO (Pendiente de decisión del usuario)
> La especificación exhaustiva de 5 fases de la Tarea 4.4 (Perfilado Doctrinal Dinámico) se encuentra detallada en [`docs/14_PLAN_PERFILADO_UNIDADES_IA.md`](../14_PLAN_PERFILADO_UNIDADES_IA.md). Se preserva íntegramente conforme a la directiva de no eliminación de párrafos.

- **Tarea 4.4 Consolidada 🟢**: Fases 1 a 5 implementadas en v2.4.5:
  - F1: Esquema canónico en catálogo `unit_catalog.json` y contratos de tipos en `unit_type.py`.
  - F2: Expansión sensorial y canales doctrinales (32..35).
  - F3: Mutación dinámica de roles en `macro_planner.py` y modulación de priors MCTS.
  - F4: Telemetría forense en DuckDB/Parquet y visualización interactiva en dashboard MLOps (:8778).
  - F5: Suite de tests unitarios e integración en verde (`test_doctrine_sensory_contract.py`, `test_doctrine_telemetry_forensics.py`).
