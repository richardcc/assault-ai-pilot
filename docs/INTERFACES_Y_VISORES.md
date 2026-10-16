# Guía de Interfaces de Usuario, Visores y Simulador

Este documento detalla la utilidad, arquitectura y comandos de arranque de las tres interfaces de usuario y visores principales del proyecto **Assault**:

1. **Visor de Modelos y Currículum (MLOps Viewer Activo - Puerto 8777)**
2. **Visor Histórico de Evaluaciones (Legacy SB3 Eval Viewer - Puerto 8765)**
3. **Simulador Táctico e Interfaz de Juego (Assault AI Tactical UI - Puerto 5173 / Backend 8001)**

---

## Comparativa Rápida

| Interfaz | URL Principal | Backend / Servicio | Utilidad Principal |
| :--- | :--- | :--- | :--- |
| **Visor Activo de Modelos (V2)** | `http://127.0.0.1:8777/` | `mlops.reporting.viewer` (Python + DuckDB/Parquet) | Catálogo de checkpoints, métricas de entrenamiento, curvas de aprendizaje, replays paso a paso, trazabilidad de fases del currículum y ranking Elo. |
| **Visor Legacy SB3** | `http://127.0.0.1:8765/` | `scripts/sb3_eval_viewer.py` | Auditoría de informes por lotes generados por Stable-Baselines3 (`metrics_sb3_report_*.json`), tasas de victoria, canales CNN, XAI y control PM2. |
| **Simulador / Modo Jugar** | `http://localhost:5173/` | Vite React (`assault_ai_ui`) + FastAPI (`assault_backend` :8001) | Tablero interactivo táctico (PixiJS), partidas Humano vs IA o IA vs IA, control de niebla de guerra, LOS, dados y copiloto RAG de reglas. |

---

## 1. Visor Activo de Modelos y Currículum (Puerto 8777)

### Utilidad
Es la herramienta central y moderna de observabilidad de modelos y ciclos de entrenamiento (especialmente **EfficientZero V2** y currículums por fases):
- **Explorador de Modelos**: Permite inspeccionar cualquier checkpoint específico con parámetros de consulta:
  `http://127.0.0.1:8777/model?engine=efficientzero_v2&model=<model_id>`
- **Métricas de Entrenamiento y Evaluación**: Curvas de pérdidas (valor, política, representación, dinámica), ratios de victoria contra diferentes oponentes (Self vs Self, Self vs Random) y métricas de objetivos (conversión de puntos de victoria VP, capturas).
- **Reproductor de Replays**: Visualizador detallado de secuencias de turnos y acciones paso a paso.
- **Trazabilidad de Currículum y Elo**: Historial de promociones entre fases y evaluación relativa en rating Elo (`/elo`).
- **Arquitectura de Alto Rendimiento**: Frontend React precompilado (`mlops/reporting/viewer_frontend`) alimentado por DuckDB y Parquet para lectura instantánea de grandes volúmenes de métricas.

### Cómo se arranca

#### Opción A: Script PowerShell recomendado (con recarga automática)
```powershell
cd C:\repos\python\assault

# Arranque estándar
.\scripts\run_curriculum_reporting_viewer.ps1

# Modo desarrollo (se reinicia automáticamente ante cambios de código)
.\scripts\run_curriculum_reporting_viewer.ps1 -Dev

# Abre el navegador automáticamente
.\scripts\run_curriculum_reporting_viewer.ps1 -OpenWindow
```

#### Opción B: Ejecución directa en Python (y compilación de frontend si se modificó)
Si se realizaron modificaciones en la interfaz React:
```powershell
cd C:\repos\python\assault\mlops\reporting\viewer_frontend
npm run build

cd C:\repos\python\assault
python -m mlops.reporting.viewer --repo-root . --host 127.0.0.1 --port 8777
```

---

## 2. Visor Histórico de Evaluaciones SB3 (Puerto 8765)

### Utilidad
Diseñado para la auditoría y análisis de evaluaciones por lotes procedentes de **Stable-Baselines3** y de las primeras fases de investigación:
- **Directorio de Informes**: Lee automáticamente los informes JSON de `C:\repos\python\assault\assault_sim\session\reports\sb3_eval\metrics_sb3_report_*.json`.
- **Métricas Tácticas Históricas**:
  - `win_rate`, `true_win_rate`, `loss_rate` y `draw_rate` desglosados por bando y escenario.
  - Métricas de misión: `vp_entry_conversion_rate`, `capture_conversion_after_contact`, `reaction_fire_count`.
  - Distribución de políticas (`sb3_kept` vs `planner_override` vs `finalizer_override`).
- **XAI y Canales**: Visualización de decisiones explicables (`xai_decisions.jsonl`) y previsualización de canales de observación 2D del mapa.
- **Panel de Control de Servicios**: Permite monitorizar el estado y reiniciar procesos mediante la API de PM2.

### Cómo se arranca

#### Opción A: Ejecución directa con Python
```powershell
cd C:\repos\python\assault

# Activar entorno virtual
.\.venv\Scripts\Activate.ps1

# Lanzar el servidor en puerto 8765
python scripts/sb3_eval_viewer.py --host 127.0.0.1 --port 8765
```
*(Por defecto tomará `assault_sim\session\reports\sb3_eval`, pero puede apuntarse a otra carpeta con `--reports-dir`).*

#### Opción B: A través de PM2
```powershell
cd C:\repos\python\assault
pm2 start ecosystem.config.cjs --only assault-sb3-viewer
```

---

## 3. Simulador e Interfaz Táctica para Jugar (Vite :5173 / Backend :8001)

### Utilidad
Es la **interfaz táctica jugable e interactiva** completa del juego sobre mapa de hexágonos:
- **Jugar contra la IA o IA vs IA**: Permite seleccionar bando (US vs IT/GE), escoger escenario táctico y enfrentar a un jugador humano contra modelos entrenados o poner dos modelos a combatir.
- **Motor Gráfico PixiJS**: Renderizado acelerado por hardware de hexágonos, terrenos (elevaciones, bosques, caminos, ciudades), apilamiento de fichas y líneas de visión (LOS).
- **Mecánicas Tácticas Completas**:
  - Movimiento por puntos de acción y restricciones de terreno.
  - Combate a distancia y asalto cuerpo a cuerpo con dados, cálculo de factores de combate y modificadores DRM.
  - Fuego de reacción (Reaction Fire) durante el turno del oponente.
  - Niebla de guerra (Fog of War) y detección de unidades.
- **Paneles Flotantes**:
  - Registro de combate en tiempo real (`tactical-log`).
  - Intel y situación táctica de unidades (`tactical-intel` / `tactical-status`).
  - Copiloto RAG integrado con el reglamento del juego (`tactical-rules`).

### Cómo se arranca

Para funcionar requiere que tanto el **backend FastAPI** (lógica del simulador y pesos del modelo) como el **frontend Vite** estén en ejecución:

#### Opción A: Arranque manual en dos terminales de PowerShell

**Terminal 1 — Backend FastAPI:**
```powershell
cd C:\repos\python\assault
.\.venv\Scripts\Activate.ps1
python -m uvicorn assault_backend.main:app --host 127.0.0.1 --port 8001 --reload
```

**Terminal 2 — Frontend UI (Vite):**
```powershell
cd C:\repos\python\assault\assault_ai_ui
npm run dev -- --host
```
*Una vez iniciado, abre tu navegador en `http://localhost:5173/`.*

#### Opción B: Arranque orquestado con PM2
El archivo `ecosystem.config.cjs` tiene preconfigurados ambos servicios:
```powershell
cd C:\repos\python\assault

# Levantar backend y frontend simultáneamente
pm2 start ecosystem.config.cjs --only "assault-backend,assault-frontend"

# Comprobar estado de los procesos
pm2 status

# Ver logs en tiempo real
pm2 logs
```

---

## Resumen de Puertos y URLs Locales

| Puerto | Protocolo | Descripción |
| :--- | :--- | :--- |
| **8777** | HTTP | Visor Activo V2 de Modelos y Currículum (`mlops.reporting.viewer`) |
| **8765** | HTTP | Visor Histórico SB3 Eval Viewer (`scripts/sb3_eval_viewer.py`) |
| **5173** | HTTP | Frontend Táctico para Jugar (`assault_ai_ui` - Vite Dev Server) |
| **8001** | HTTP | Backend de Simulación y API de Juego (`assault_backend` - FastAPI) |

---

## Arranque Todo-en-Uno en Pestanas (PowerShell / Windows Terminal)

Existe un script automatizado para levantar todas las interfaces y entornos a la vez:

`powershell
cd C:\repos\python\assault
.\start_all_environments.ps1
`

Abre una sola ventana de **Windows Terminal** con 6 pestanas etiquetadas:
1. `Reporting-8777`: Visor moderno de modelos y curriculum.
2. `SB3-Viewer-8765`: Visor historico de evaluaciones SB3.
3. `Backend-8001`: FastAPI backend con recarga activa.
4. `TacticalUI-5173`: Frontend interactivo Vite para jugar.
5. `Dev-1 (venv)`: Terminal libre con el entorno virtual activo.
6. `Dev-2 (venv)`: Segunda terminal libre con el entorno virtual activo.

*(Si no se dispone de Windows Terminal o se ejecuta con -SeparateWindows, abrira las ventanas independientes correspondientes).*
