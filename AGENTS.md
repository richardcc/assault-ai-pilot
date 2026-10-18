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
