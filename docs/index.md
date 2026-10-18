# Portal Canónico de Documentación — Assault Wargame & AI Platform

Bienvenido al portal oficial de documentación técnica del proyecto **Assault**, plataforma integral de simulación táctica militar por turnos sobre tablero hexagonal e inteligencia artificial militar basada en **EfficientZero V2**.

> [!NOTE]
> **Arquitectura Activa:** Todo el entrenamiento, autojuego, inferencia y MCTS operan exclusivamente sobre **EfficientZero V2** (`agents/efficientzero_v2/`). El stack legacy MuZero v1 se encuentra 100% decomisionado.

---

## 🗺️ Mapa de Navegación del Sistema

```mermaid
graph TD
    ROOT["Assault Wargame & AI Platform"]
    
    C1["1. Arquitectura del Sistema"]
    C2["2. Reglas Tácticas y VOEC"]
    C3["3. EfficientZero V2"]
    C4["4. MLOps y Telemetría"]
    C5["5. Hoja de Ruta (Roadmap)"]
    C6["6. Auditoría Palma et al. 2025"]
    C7["7. Copilot RAG"]
    C8["8. Backend y APIs"]
    C9["9. Auditoría Reglamento vs Engine"]
    
    ROOT --> C1
    ROOT --> C2
    ROOT --> C3
    ROOT --> C4
    ROOT --> C5
    ROOT --> C6
    ROOT --> C7
    ROOT --> C8
    ROOT --> C9
```

---

## 📚 Módulos Canónicos de Documentación

### 1. [Arquitectura del Sistema](01_ARQUITECTURA_DEL_SISTEMA.md)
* **Principios de diseño:** Desacoplamiento estricto por contratos entre capas.
* **Subsistemas:** `assault_model` (reglas puras autoritativas), `voec_sim` (observación sensorial y simulación), `agents/efficientzero_v2` (red neuronal e inferencia MCTS) y `mlops` (telemetría y linaje).
* **Ciclo de vida:** Flujo de autojuego (*self-play*), reincorporación a buffer de repeticiones y entrenamiento distribuido.

### 2. [Modelo del Juego y Reglas Tácticas](02_MODELO_DEL_JUEGO_Y_REGLAS_TACTICAS.md)
* **Geometría hexagonal:** Coordenadas axiales $(q, r)$, métricas de distancia y adyacencia.
* **Terreno y balística:** Catálogo de terrenos, cobertura, cálculo 3D de Línea de Visión (LOS) y Niebla de Guerra (*POMDP*).
* **Mecánica de combate:** Dados de batalla (Rojo, Azul, Verde, Amarillo), tiradas de salvación y asignación de bajas.
* **Psicología militar:** Estados de cohesión y moral (`NORMAL`, `PINNED`, `SUPPRESSED`, `ROUTED`), fuego de reacción (*Opportunity Fire*) y combate cerrado (*Close Combat*).

### 3. [Red Neuronal y Algoritmo EfficientZero V2](03_RED_NEURONAL_EFFICIENTZERO_V2.md)
* **Modelo de mundo recurrente:** Funciones de representación $h_\theta$, dinámica $g_\theta$, predicción $f_\theta$ y consistencia temporal $q_\theta$.
* **Convoluciones hexagonales:** `HexagonalMaskConv2d` para eliminación de artefactos direccionales espurios.
* **Cabezas auxiliares:** Mapa 2D de amenazas (`threat_map`), balance de bajas (`attrition`) y estimación de cohesión (`morale`).
* **Representaciones de valor:** Two-Hot simétrico, **HL-Gauss** (*Histogram Loss with Gaussian Targets*, DeepMind 2024) y compresión **Symlog**.
* **HRL y optimización:** Planificador jerárquico Macro (Nivel 1), búsqueda MCTS PUCT / Gumbel y balanceo de gradientes mediante **PCGrad**.

### 4. [Plataforma MLOps, Telemetría y Reporting](04_PLATAFORMA_MLOPS_Y_TELEMETRIA.md)
* **Almacenamiento analítico:** Registro columnar de partidas en Apache Parquet y base de datos OLAP **DuckDB**.
* **Puertas de promoción:** Reglas automatizadas (*Promotion Gates*) para validación de checkpoints contra baselines.
* **Visor Web MLOps (Puerto 8778):** Catálogo de modelos, simulador de unroll del espacio latente, atribución de canales y reproductor paso a paso de partidas (*Match Replay*).

### 5. [Hoja de Ruta Evolutiva (Roadmap 2024–2026)](05_ROADMAP_EVOLUTIVO.md)
* **Fases técnicas:** De la Fase 1 a la 4 (completadas) a la Fase 5 (curriculum táctico y HRL multiescala).
* **Matriz de hitos:** Entregables, dependencias y criterios de éxito del sistema de autoaprendizaje.

### 6. [Auditoría Científica: Hex-Wargame AI (Palma et al. 2025) vs. Assault](06_LITERATURE_AUDIT_CHANNELS_HEADS_TACTICS.md)
* **Estudio comparativo exhaustivo:** Evaluación frente al paper seminal de Palma et al. (Feb 2025 / arXiv:2502.13918v1).
* **Módulo de aprendizaje:** Model-Based EfficientZero V2 vs. Model-Free AlphaZero con RNNs; análisis de muestra-eficiencia y ratios de convergencia.
* **Profundidad táctica:** Wargame militar VOEC (balística real, blindaje direccional, moral, supresión, overwatch) vs. Simple Conflict Simulation (SCS).
* **Lecciones asimiladas:** Invariancia topológica mediante generación procedural y normalización de canales.

### 7. [Sistema RAG Copilot y Explicabilidad Normativa](06_SISTEMA_RAG_COPILOT.md)
* **Base de conocimiento unificada:** 114 fragmentos de reglamento y 24 fragmentos de catálogo técnico en `assault_rag/`.
* **Motor de búsqueda híbrido:** BM25 balanceado con scoring por relevancia de sección y normalización bilingüe.
* **Servicios tácticos:** Consultas normativas (`rag_query`), reporte de situación (`explain_game_situation` SitRep en vivo), recomendaciones tácticas consultivas y análisis de partidas.
* **Motor generativo dual:** Soporte para LLM local (Ollama `qwen2.5:14b`) con fallback extractivo instantáneo de alta precisión.

### 8. [Servicios Backend y Catálogo de APIs](07_SERVICIOS_BACKEND_Y_CATALOGO_APIS.md)
* **Documentación interactiva OpenAPI:** [Swagger UI](http://127.0.0.1:8001/docs) y [ReDoc](http://127.0.0.1:8001/redoc).
* **Servicio de Simulación Táctica (`:8001`):** Endpoints REST para ciclos de juego, combate y canal bidireccional WebSocket (`/ws/game`).
* **Servicio RAG Copilot (`/api/rag/*`):** Endpoints de asistencia, consulta normativa y estado del LLM.
* **Servicio de Telemetría MLOps (`:8778`):** DuckDB REST API, visor de métricas y servidor de documentación estática integrada.

### 9. [Auditoría Exhaustiva: Reglamento Oficial vs. Engine y Escenarios](08_AUDITORIA_REGLAMENTO_VS_ENGINE.md)
* **Auditoría página a página del Manual de Reglas:** 52 páginas del *Rulebook rev6* auditadas respecto a `assault_model/`.
* **Auditoría del Compendio de Escenarios:** Análisis de los 38 escenarios oficiales (26 de la Campaña de Gela + 12 Standalone) frente al catálogo modelado en JSON.
* **Plan de paridad 100%:** Fases priorizadas para implementación de soporte táctico (TAS/OAS), cartas de mando y transporte.

---

## 🚀 Servicios en Vivo y Puertos Locales

| Servicio | Puerto | Descripción | URL Directa |
| :--- | :---: | :--- | :--- |
| **Documentación Central** | `8778` | MkDocs Material Portal Canónico | [http://127.0.0.1:8778/docs/](http://127.0.0.1:8778/docs/) |
| **Visor Web MLOps** | `8778` | Dashboard de modelos, métricas y replays | [http://127.0.0.1:8778/](http://127.0.0.1:8778/) |
| **Backend Táctico FastAPI** | `8001` | API de simulación, combate y RAG | [http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs) |
| **Simulador UI (Vite / React)** | `5173` | Tablero hexagonal interactivo | [http://127.0.0.1:5173/](http://127.0.0.1:5173/) |
