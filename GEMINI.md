# DIRECTIVAS DE DESARROLLO Y EXPERIMENTACIÓN (ASSAULT PROJECT)

## ⚠️ REGLA ESTRICTA E INQUEBRANTABLE: MUZERO ESTÁ DECOMISIONADO

1. **ESTADO DE MUZERO:**
   - **MuZero (v1 / clásico) está 100% DECOMISIONADO y OBSOLETO.**
   - **NO se usa** para entrenar, ni para evaluar, ni para correr benchmarks o pruebas.
   - Cualquier intento de usar MuZero legacy en lugar de EfficientZero es considerado un error crítico.

2. **AGENTE ESTÁNDAR EXCLUSIVO: EFFICIENTZERO (EFFICIENTZERO V2):**
   - **TODO** entrenamiento (`trainer.py`), evaluación, self-play, simulación, inferencia y MCTS debe realizarse exclusivamente con **`EfficientZeroV2`** (`agents/efficientzero_v2/`).
   - Las mejoras de arquitectura (Two-hot value/reward, Spatial Attention, cabezas tácticas: `threat_map`, `attrition`, `morale`, balanceo adaptativo PCGrad/GradNorm) residen y operan únicamente en EfficientZero v2.

3. **PRUEBAS Y VERIFICACIONES:**
   - Las pruebas de desarrollo y experimentación deben correr sobre:
     `agents/efficientzero_v2/tests/`
   - No ejecutar ni basar nuevos desarrollos en el stack heredado de MuZero.

4. **SINCRONIZACIÓN 100% OBLIGATORIA MD -> HTML (`docs/index.html` Y `site/`):**
   - **REGLA A FUEGO:** El HTML de documentación (`docs/index.html` y el sitio compilado en `site/`) **SIEMPRE** debe contener el **100% íntegro y exacto** de todo el contenido de los archivos `.md` de `docs/`.
   - **La Hoja de Ruta Evolutiva (`05_ROADMAP_EVOLUTIVO.md`) debe ser SIEMPRE el último punto (`09. Hoja de Ruta Evolutiva (Roadmap)`)** de la documentación y unificar cualquier apartado de roadmap.
   - **Acción obligatoria tras cualquier cambio en `docs/*.md`:** Ejecutar siempre `python scripts/sync_docs_html.py` para inyectar el 100% de los `.md` en `docs/index.html` (`embeddedDocsData`) y regenerar `site/` con `mkdocs build`.

5. **CERO RETROCOMPATIBILIDAD CON MUZERO (CLEAN BREAK):**
   - **Tolerancia Cero a la Deuda Técnica:** Queda terminantemente prohibido mantener compatibilidad hacia atrás (*shims*, alias de transición o adaptadores tolerantes) con MuZero.
   - Toda nomenclatura, perfiles de benchmark (`ezv2_selfplay`, `ezv2_vs_random_side_a`, `ezv2_vs_random_side_b`), adaptadores (`EZV2VOECAdapter`), pipelines de evaluación y configuraciones deben ser 100% nativos y puros de EfficientZero V2.

6. **RIGOR METODOLÓGICO, DOCUMENTACIÓN Y HOJA DE RUTA OBLIGATORIA:**
   - **TODO cambio o mejora debe seguir estrictamente las normas del proyecto:** Arquitectura limpia desacoplada por contratos, suite de tests unitarios/integración en verde y tipado estricto.
   - **Documentación Inmediata:** Ninguna funcionalidad, cambio de modelo o refactorización se considera terminada si no queda documentada en el módulo Markdown canónico correspondiente en `docs/`.
   - **Actualización Obligatoria del Roadmap:** Cualquier cambio en el alcance, nueva funcionalidad, hito alcanzado o modificación de prioridades **DEBE registrarse y anotarse explícitamente en la Hoja de Ruta Evolutiva (`docs/05_ROADMAP_EVOLUTIVO.md`)**.
   - **Observabilidad y Monitorización en Dashboard (Puerto 8778):** Si la funcionalidad o mejora genera nuevas métricas, estados o decisiones tácticas (ej. roles de unidad, perfiles, pérdidas, gates), **DEBE quedar integrada en la telemetría DuckDB/Parquet y visualizada en el Dashboard MLOps** para su monitorización en tiempo real y replay forense.
   - **Sincronización:** Tras cualquier cambio en la documentación o roadmap, ejecutar inmediatamente `python scripts/sync_docs_html.py`.

7. **POLÍTICA ESTRICTA DE IDIOMAS (UI Y CÓDIGO EN INGLÉS, USUARIO Y DOCS EN ESPAÑOL):**
   - **Interfaz de Usuario (UI) 100% en Inglés:** Todos los componentes de frontend, vistas, paneles de control (MLOps Dashboard, visores de replay, inspectores), botones, etiquetas, tooltips, modales, gráficos, encabezados y mensajes de estado DEBEN estar estrictamente en inglés. Queda terminantemente prohibido mostrar textos en español en cualquier elemento de la interfaz de usuario.
   - **Código Fuente 100% en Inglés:** Todo el código (Python, JavaScript, TypeScript, HTML, CSS, SQL), nombres de variables, funciones, clases, constantes, docstrings, comentarios dentro del código, logs de ejecución (`logger`, `print`), excepciones y aserciones DEBEN escribirse exclusivamente en inglés.
   - **Interacción con el Usuario en Español:** Las respuestas, explicaciones, preguntas y diálogo de pair programming con el usuario se realizan siempre en español.
   - **Documentación Técnica Canónica (`docs/`):** La documentación técnica de arquitectura, especificaciones de reglas y la hoja de ruta evolutiva (`docs/05_ROADMAP_EVOLUTIVO.md`) se redactan de momento en español.
   - **Estrategia de Corrección Oportunista (Sin barrido masivo retroactivo):** NO se realizará una revisión masiva de todo el repositorio existente únicamente para traducir. Sin embargo, **CADA VEZ que se modifique o extienda un archivo de código o componente de UI**, es OBLIGATORIO corregir y traducir al inglés cualquier texto residual en español que se encuentre en dicho archivo o módulo. A partir de ahora, jamás se introducirá español en código ni en interfaz de usuario.




